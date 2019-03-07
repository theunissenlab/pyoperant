from ctypes import *
from contextlib import contextmanager
import os
import logging
import threading
import numpy as np
import scipy.io.wavfile

import pyaudio
import queue
import wave
from pyoperant.interfaces import base_
from pyoperant import InterfaceError
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
            break
        except OSError:
            continue
    asound.snd_lib_error_set_handler(c_error_handler)
    yield
    asound.snd_lib_error_set_handler(None)


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
        self.stream = None
        self.wf = None
        self.rate = input_rate
        self.callback = None
        self._playing_wav = threading.Event()
        self._recording = threading.Event()
        self.rec_queue = None
        self.ongoing_threads = []
        self.abort_signal = threading.Event()
        self.open()

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
        for t in self.ongoing_threads:
            t.join()

        try:
            self.stream.close()
        except AttributeError:
            self.stream = None
        try:
            self.wf.close()
        except AttributeError:
            self.wf = None
        self.pa.terminate()

    def _get_stream(self, start=False, event=None, **kwargs):
        """
        """
        def _callback(in_data, frame_count, time_info, status):
            if not self._playing_wav.is_set():
                return (None, pyaudio.paComplete)

            try:
                cont = self.callback()
            except TypeError:
                cont = True

            if cont:
                data = self.wf.readframes(frame_count)
                return (data, pyaudio.paContinue)
            else:
                return (None, pyaudio.paComplete)

        self.stream = self.pa.open(format=self.pa.get_format_from_width(self.wf.getsampwidth()),
                                   channels=self.wf.getnchannels(),
                                   rate=self.wf.getframerate(),
                                   output=True,
                                   output_device_index=self.device_index,
                                   start=False,
                                   stream_callback=_callback)

        if start:
            self._play_wav(event=event)

    def _run_record(self, duration=None, dest=None, quit_signal=None, abort_signal=None):
        chunk = 2048
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
        self.ongoing_threads.append(t)
        t.start()
        return t, new_quit_signal

    def _stop_record(self, event=None, thread=None, quit_signal=None, **kwargs):
        if quit_signal is not None:
            quit_signal.set()

    def _queue_wav(self, wav_file, start=False, event=None, **kwargs):
        logger.debug("Queueing wavfile %s" % wav_file)
        self.wf = wave.open(wav_file)
        self.validate()
        self._get_stream(start=start, event=event)

    def _play_wav(self, event=None, **kwargs):
        logger.debug("Playing wavfile")
        self._playing_wav.set()
        events.write(event)
        self.stream.start_stream()

    def _stop_wav(self, event=None, **kwargs):
        self._playing_wav.clear()
        try:
            logger.debug("Attempting to close pyaudio stream")
            events.write(event)
            self.stream.stop_stream()
            self.stream.close()
            logger.debug("Stream closed")
        except AttributeError:
            self.stream = None
        try:
            self.wf.close()
        except AttributeError:
            self.wf = None

if __name__ == "__main__":

    with log_alsa_warnings():
        pa = pyaudio.PyAudio()
    pa.terminate()
    print "-" * 40
    pa = pyaudio.PyAudio()
    pa.terminate()
