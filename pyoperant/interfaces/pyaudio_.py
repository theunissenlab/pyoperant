
from ctypes import *
from contextlib import contextmanager
import os
import logging
import sys
import queue
import threading
import numpy as np
import scipy.io.wavfile
import time

import pyaudio
import wave
from pyoperant.interfaces import base_
from pyoperant import InterfaceError, utils
from pyoperant.events import events


REC_CHUNK = 1024


logger = logging.getLogger(__name__)
# TODO: Clean up _stop_wav logging changes


def get_audio_devices():
    pa = pyaudio.PyAudio()
    devices = [
        pa.get_device_info_by_index(index)
        for index in range(pa.get_device_count())
    ]
    return {info["name"]: info for info in devices}


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


class RecordBuffer(object):
    """Buffers a fixed amount of data

    When maxlen is set to None with set_maxlen(None)
    the buffer will continue to accumulate indefinitely
    """
    def __init__(self, maxlen=0):
        self.maxlen = maxlen
        self.start = 0
        self.length = 0
        self.data = None

    def __len__(self):
        return self.length

    def __array__(self):
        if self.data is None:
            return np.array([])
        else:
            return self.data[-self.length:]

    def clear(self):
        self.data = None
        self.length = 0

    def set_maxlen(self, maxlen=None):
        """Set maxlen and adjust data array size"""
        self.maxlen = maxlen

        if self.data is not None and len(self.data) == self.maxlen:
            return

        if self.maxlen > 0:
            if len(self.data) > self.maxlen:
                self.data = self.data[-self.maxlen:]
                self.length = min(self.length, self.maxlen)
            else:
                extended_data = np.zeros((self.maxlen, self.data.shape[1]))
                extended_data[-len(self.data):] = self.data
                self.length = len(self.data)
                self.data = extended_data
        elif self.data is not None:
            self.data = self.data[-self.length:]

    def extend(self, data):
        to_add = np.array(data)
        if to_add.ndim == 1:
            to_add = to_add[:, None]

        if self.data is None:
            if self.maxlen > 0:
                self.data = np.zeros((self.maxlen, to_add.shape[1]))
                self.length = 0
            else:
                self.data = np.zeros((0, to_add.shape[1]))
                self.length = 0

        # Validate that the dimensions are correct
        if self.data.shape[1] != to_add.shape[1]:
            raise ValueError("Cannot extend array with incompatible shape")

        if self.maxlen > 0:
            if len(data) >= self.maxlen:
                self.data[:] = to_add[:-self.maxlen:]
                self.length = len(self.data)
            else:
                self.data = np.roll(self.data, -len(to_add))
                self.data[-len(to_add):] = to_add
                self.length = min(self.maxlen, self.length + len(to_add))
        else:
            self.data = np.concatenate([self.data, to_add])
            self.length = len(self.data)


class PyAudioInterface(base_.AudioInterface):
    """Class which holds information about an audio device

    assign a simple callback function that will execute on each frame
    presentation by writing interface.callback

    interface.callback() should return either True (to continue playback) or
    False (to terminate playback)

    Before assigning any callback function, please read the following:
    https://www.assembla.com/spaces/portaudio/wiki/Tips_Callbacks

    """
    def __init__(self, device_name="default", is_mic=False, *args, **kwargs):
        super().__init__(*args,**kwargs)
        self.device_name = device_name
        self.device_index = None
        self.wf = None
        self.rate = None
        self.callback = None
        self.abort_signal = threading.Event()
        self.open()
        self.gain = None
        self.play_thread = None
        self._playback_quit_signal = None
        self._playback_lock = threading.Lock()

        if is_mic:
            self.record_queue = queue.Queue()
            self.rec_stream = None
            self._record_buffer = RecordBuffer(maxlen=24000)
            self.listen()

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
        self.rate = int(self.device_info["defaultSampleRate"])

    def close(self):
        if not sys.is_finalizing():
            logger.debug("Closing device")

        self.abort_signal.set()
        self.abort_signal = threading.Event()

        try:
            self.rec_stream.close()
        except:
            pass

        try:
            self.wf.close()
        except AttributeError:
            self.wf = None
        self.pa.terminate()

    def _run_play(self, wf=None, quit_signal=None, abort_signal=None):
        """Function to play back a sound

        Plays back a sound in chunks of 512 until the wav file is completed
        or a quit_signal or abort_signal is received.

        Parameters
        ----------
        wf : wav file opened with wave.open
        quit_signal : threading.Event
            thread-safe signal that will end the playback when the event is set
        abort_signal : threading.Event
            thread-safe signal that will end the playback when the event is set
        """
        chunk = 1024

        try:
            stream = self.pa.open(
               format=self.pa.get_format_from_width(wf.getsampwidth()),
               channels=wf.getnchannels(),
               rate=wf.getframerate(),
               output=True,
               frames_per_buffer=chunk,
               output_device_index=self.device_index,
            )
        except IOError:
            logging.error("IOError on opening pa stream. Not sure why")
            raise

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

            if self.gain:
                data = data * np.power(10.0, self.gain / 20.0)

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
                "quit_signal": new_quit_signal,
                "abort_signal": self.abort_signal
            }
        )
        self.play_thread = new_thread

        if start:
            self._play_wav(event=event)

        self.wf = None

        return new_quit_signal

    def rec_callback(self, in_data, frame_count, time_info, status):
        data = np.frombuffer(in_data, dtype=np.int16)
        self._record_buffer.extend(data)
        if self._record_buffer.maxlen == 0:
            self.record_queue.put(data)
        return in_data, pyaudio.paContinue

    def listen(self):
        """Start microphone recording stream
        """
        self.rec_stream = self.pa.open(format=pyaudio.paInt16,
            channels=1,
            rate=self.rate,
            input_device_index=self.device_index,
            input=True,
            output=False,
            frames_per_buffer=REC_CHUNK,
            stream_callback=self.rec_callback
        )

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
        self._record_buffer.set_maxlen(0)
        _recording_started_at = self._record_buffer.length

        while not quit_signal.is_set() and not abort_signal.is_set():
            time.sleep(0.01)

        _t = time.time()
        while (time.time() - _t) < duration and not abort_signal.is_set():
            time.sleep(0.01)

        self._record_buffer.set_maxlen(24000)
        recorded_data = []
        while not self.record_queue.empty():  # or 'while' instead of 'if'
            item = self.record_queue.get()
            recorded_data.append(item)
        recorded_data = np.concatenate(recorded_data)
        # recorded_data = self._record_buffer.data[_recording_started_at:]

        if not os.path.exists(os.path.dirname(dest)):
            os.makedirs(os.path.dirname(dest))
        logger.debug("Finished recording, writing to {}".format(dest))

        scipy.io.wavfile.write(
            dest,
            self.rate,
            recorded_data
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

    def _stop_record(self, event=None, quit_signal=None, **kwargs):
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
            event=event
        )

    def _play_wav(self, event=None, gain=None, **kwargs):
        logger.debug("Playing wavfile")
        events.write(event)

        self.set_gain(gain)

        if self.play_thread is not None:
            self.play_thread.start()

    def _stop_wav(self, event=None, **kwargs):
        self._playback_quit_signal.set()
        self.play_thread = None


from unittest import mock

class MockPyAudioInterface(PyAudioInterface):
    pass
    # def open(self):
        # """Don't actually locate an audio device"""
        # self.pa = pyaudio.PyAudio()
        # Get the default audio device here instead...
        # with mock.patch("pyaudio.PyAudio.get_device_info_by_index", return_value={"name": self.device_name}):
            # return super().open()



if __name__ == "__main__":

    with log_alsa_warnings():
        pa = pyaudio.PyAudio()
    pa.terminate()
    print("-" * 40)
    pa = pyaudio.PyAudio()
    pa.terminate()
