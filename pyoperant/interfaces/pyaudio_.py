from ctypes import *
from contextlib import contextmanager
import os
import logging
import threading
import numpy as np
import scipy.io.wavfile
import time

import pyaudio
import wave
from pyoperant.interfaces import base_
from pyoperant import InterfaceError, utils
from pyoperant.events import events


logger = logging.getLogger(__name__)
# TODO: Clean up _stop_wav logging changes


# Modify the alsa error function to suppress needless warnings
# Code derived from answer by Nils Werner at:
# http://stackoverflow.com/questions/7088672/pyaudio-working-but-spits-out-error-messages-each-time
# TODO: Pass actual warnings to logger.debug when logging is fully integrated into master.
@contextmanager
def log_alsa_warnings():
    """ Suppresses ALSA warnings when initializing a PyAudio instance.

    with log_alsa_warnings():
        pa = pyaudio.PyAudio()
    """
    # Set up the C error handler for ALSA
    ERROR_HANDLER_FUNC = CFUNCTYPE(None,
                                   c_char_p,
                                   c_int,
                                   c_char_p,
                                   c_int,
                                   c_char_p,
                                   c_char_p)

    def py_error_handler(filename, line, function, err, fmt, args):

        # ALSA_STR = "ALSA lib %s:%i:(%s) %s"

        # Try to format fmt with args. As far as I can tell, CFUNCTYPE does not
        # support variable number of arguments, so formatting will fail with
        # TypeError if fmt has multiple %'s.
        # if args is not None:
        #     try:
        #         fmt %= args
        #     except TypeError:
        #         pass
        # logger.debug(ALSA_STR, filename, line, function, fmt)
        pass

    c_error_handler = ERROR_HANDLER_FUNC(py_error_handler)
    for asound_library in ["libasound.so", "libasound.so.2"]:
        try:
            asound = cdll.LoadLibrary(asound_library)
        except OSError:
            continue
        else:
            asound.snd_lib_error_set_handler(c_error_handler)
            yield
            asound.snd_lib_error_set_handler(None)
            break
    else:
        yield


class PyAudioInterface(base_.AudioInterface):
    """Class which holds information about an audio device

    assign a simple callback function that will execute on each frame
    presentation by writing interface.callback

    interface.callback() should return either True (to continue playback) or
    False (to terminate playback)

    Before assigning any callback function, please read the following:
    https://www.assembla.com/spaces/portaudio/wiki/Tips_Callbacks

    """
    def __init__(self, device_name="default", input_rate=44100, *args, **kwargs):
        super(PyAudioInterface, self).__init__(*args,**kwargs)
        self.device_name = device_name
        self.device_index = None
        self.wf = None
        self.rate = input_rate
        self.callback = None
        self.abort_signal = threading.Event()
        self.open()
        self.gain = None
        self.play_thread = None
        self._playback_quit_signal = None
        self._playback_lock = threading.Lock()

    def set_gain(self, gain):
        self.gain = gain

    def open(self):
        with log_alsa_warnings():
            self.pa = pyaudio.PyAudio()
        for index in range(self.pa.get_device_count()):
            if self.device_name == self.pa.get_device_info_by_index(index)['name']:
                logger.debug("Found device %s at index %d" % (self.device_name, index))
                self.device_index = index
                break
            else:
                self.device_index = None
        if self.device_index == None:
            raise InterfaceError('could not find pyaudio device %s' % (self.device_name))

        self.device_info = self.pa.get_device_info_by_index(self.device_index)

    def close(self):
        logger.debug("Closing device")
        self.abort_signal.set()
        self.abort_signal = threading.Event()

        try:
            self.wf.close()
        except AttributeError:
            self.wf = None
        self.pa.terminate()

    def _run_play(self, wf=None, gain=None, quit_signal=None, abort_signal=None):
        """Function to play back a sound

        Plays back a sound in chunks of 512 until the wav file is completed
        or a quit_signal or abort_signal is received.

        Parameters
        ----------
        wf : wav file opened with wave.open
        gain : float
            factor by which to scale the output signal
        quit_signal : threading.Event
            thread-safe signal that will end the playback when the event is set
        abort_signal : threading.Event
            thread-safe signal that will end the playback when the event is set
        """
        chunk = 1024

        stream = self.pa.open(
           format=self.pa.get_format_from_width(wf.getsampwidth()),
           channels=wf.getnchannels(),
           rate=wf.getframerate(),
           output=True,
           frames_per_buffer=chunk,
           output_device_index=self.device_index,
        )

        data = wf.readframes(chunk)

        last_time = time.time()
        dts = []
        while data != b"":
            if quit_signal.is_set() or abort_signal.is_set():
                logger.debug("Attempting to close pyaudio stream on interrupt")
                stream.close()
                self._playback_lock.release()
                logger.debug("Stream closed")
                break

            dtype, max_val = self._get_dtype(wf)
            data = np.frombuffer(data, dtype)

            if gain:
                data = data * np.power(10.0, gain / 20.0)

            data = data.astype(dtype).tostring()
            stream.write(data)
            data = wf.readframes(chunk)
            dts.append(time.time() - last_time)
            last_time = time.time()
        else:  # This block is run when the while condition becomes False (not on break)
            logger.debug("Attempting to close pyaudio stream on file complete")
            # Extra wait at the end to make sure the whole file is played through.
            # Don't want to hold the lock for too long though.
            utils.wait(0.1)
            stream.close()
            self._playback_lock.release()
            logger.debug("Stream closed")

        logger.debug("mean={:.6f} median={:.6f} max={:.6f}".format(
            np.mean(dts),
            np.median(dts),
            np.max(dts)
        ))

        try:
            wf.close()
        except:
            logger.error("Error closing wave file. Attempting to continue")

    def _get_stream(self, start=False, event=None, **kwargs):
        """Prepare a thread to run stimulus playback

        Parameters
        ----------
        start : bool
            When set to true, automatically launch the playback thread right away
        event :
            Evenet for logging purposes
        """
        new_quit_signal = threading.Event()

        new_thread = threading.Thread(
            target=self._run_play,
            kwargs={
                "wf": self.wf,
                "gain": self.gain,
                "quit_signal": new_quit_signal,
                "abort_signal": self.abort_signal
            }
        )
        self.play_thread = new_thread

        if start:
            self._play_wav(event=event)

        self.wf = None

        return new_quit_signal

    def _run_record(self, duration=None, dest=None, quit_signal=None, abort_signal=None):
        """Record audio from pyaudio stream for a fixed duration or until a quit signal

        Parameters
        ----------
        duration : float
            Specify either the duration in seconds to record for
            (if quit_signal is not set), or the duration to record after the
            quit signal is received (padding)
        dest : str
            Path to save recorded data to
        quit_signal : threading.Event
            thread-safe signal that will end the recording when the event is set
        abort_signal : threading.Event
            thread-safe signal that will end the recording when the event is set
        """
        chunk = 1024
        stream = self.pa.open(format=pyaudio.paInt16,
            channels=1,
            rate=self.rate,
            input=True,
            output=False,
            frames_per_buffer=chunk)

        frames = []

        if quit_signal is not None:
            while not quit_signal.is_set() and not abort_signal.is_set():
                data = stream.read(chunk)
                data = np.frombuffer(data, dtype=np.int16)
                frames.append(data)

        if duration is not None:
            for i in range(0, int(self.rate / chunk * duration)):
                if abort_signal.is_set():
                    break
                data = stream.read(chunk)
                data = np.frombuffer(data, dtype=np.int16)
                frames.append(data)

        stream.close()

        if not len(frames):
            return
        data = np.concatenate(frames)

        if not os.path.exists(os.path.dirname(dest)):
            os.makedirs(os.path.dirname(dest))

        scipy.io.wavfile.write(
            dest,
            self.rate,
            data
        )

    def _record(self, event=None, duration=0, dest=None, **kwargs):
        new_quit_signal = threading.Event()

        t = threading.Thread(
            target=self._run_record,
            args=(duration,),
            kwargs={
                "dest": dest,
                "quit_signal": new_quit_signal,
                "abort_signal": self.abort_signal
            }
        )
        t.start()
        return t, new_quit_signal

    def _stop_record(self, event=None, thread=None, quit_signal=None, **kwargs):
        if quit_signal is not None:
            quit_signal.set()

    def _queue_wav(self, wav_file, start=False, event=None, **kwargs):
        if self._playback_quit_signal:
            self._playback_quit_signal.set()

        # We msut wait for the previous stream to be closed
        self._playback_lock.acquire()

        logger.debug("Queueing wavfile %s" % wav_file)
        self.wf = wave.open(wav_file)
        self.validate()
        self._playback_quit_signal = self._get_stream(
            start=start,
            gain=self.gain,
            event=event
        )
        self.set_gain(None)

    def _play_wav(self, event=None, gain=None, **kwargs):
        logger.debug("Playing wavfile")
        events.write(event)

        self.set_gain(gain)

        if self.play_thread is not None:
            self.play_thread.start()

    def _stop_wav(self, event=None, **kwargs):
        self._playback_quit_signal.set()
        self.play_thread = None

if __name__ == "__main__":

    with log_alsa_warnings():
        pa = pyaudio.PyAudio()
    pa.terminate()
    print "-" * 40
    pa = pyaudio.PyAudio()
    pa.terminate()
