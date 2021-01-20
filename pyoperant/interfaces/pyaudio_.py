
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


class RingBuffer(object):
    """A circular buffer

    Allocates space for the max buffer length. Use RingBuffer.extend(data)
    to add to the buffer and RingBuffer.to_array() to get the current contents.

    Methods
    =======
    RingBuffer.extend(data)
        Extends the buffer with a 2D numpy array
    RingBuffer.to_array()
        Return an array representation of data in the buffer (copied
        so that it can be modified without affecting the buffer)
    """
    def __init__(self, maxlen=0, n_channels=None, dtype=None):
        """Initialize circular buffer

        Params
        ======
        maxlen : int (default 0)
            Maximum size of buffer
        n_channels : int (default None)
            Enforce number of channels in buffer. If None,
            will choose the number of channels the first time .extend()
            is called.
        dtype : type (default None)
            Enforce datatype of buffer. If None,
            will choose the datatype the first time .extend()
            is called.
        """
        self.maxlen = maxlen

        # Keep track of original value for if the buffer is cleared
        self._init_n_channels = n_channels
        self.n_channels = n_channels
        self._init_dtype = dtype
        self.dtype = dtype

        # Data is stored in a numpy array of maxlen even when
        # the amount of data is smaller than that. When data
        # exceeds maxlen we loop around and keep track of where we
        # started.
        self._write_at = 0  # Where the next data should be written
        self._length = 0  # The amount of samples of real data in the buffer
        self._start = 0  # Starting index where data should be read from
        self._overlapping = False  # Has the data wrapper around the end
        self._ringbuffer = np.zeros((self.maxlen, self.n_channels or 0), dtype=self.dtype or np.int16)

    def __len__(self):
        return self._length

    def __array__(self):
        return self.to_array()

    def to_array(self):
        # Read to the end and then wrap around to the beginning
        # if self._start + self._length > self.maxlen:
        if self._overlapping:
            return np.roll(self._ringbuffer, -self._start, axis=0)
        else:
            return self._ringbuffer[:self._length].copy()

    def clear(self):
        self._write_at = 0
        self._length = 0
        self._start = 0
        self.n_channels = self._init_n_channels
        self.dtype = self._init_dtype
        self._overlapping = False
        self._ringbuffer = np.zeros((self.maxlen, self.n_channels or 0), dtype=self.dtype or np.int16)

    def extend(self, data):
        """Extend the buffer with a 2D (samples x channels) array

        Requires shape to be consistent with existing data
        """
        if self.maxlen == 0:
            return

        # Reshape 1-D signals to be 2D with one channel
        to_add = np.array(data)
        if self.dtype is None:
            self.dtype = to_add.dtype
            self._ringbuffer = self._ringbuffer.astype(self.dtype)

        if to_add.ndim == 1:
            to_add = to_add[:, None]

        # Enforce channels here
        if self.n_channels and to_add.shape[1] != self.n_channels:
            raise ValueError("Cannot extend {} channel Buffer with data of shape {}".format(
                self.n_channels,
                to_add.shape
            ))

        if self._length == 0 and self.n_channels is None:
            self._ringbuffer = np.zeros((self.maxlen, to_add.shape[1]), dtype=self.dtype)
            self.n_channels = to_add.shape[1]

        if len(to_add) > self.maxlen:
            self._ringbuffer[:] = to_add[-self.maxlen:]
            self._write_at = 0
            self._length = self.maxlen
            self._start = 0
            self._overlapping = False
        elif self._write_at + len(to_add) < self.maxlen:
            self._ringbuffer[self._write_at:self._write_at + len(to_add)] = to_add
            self._write_at += len(to_add)
            self._length = self.maxlen if self._overlapping else self._write_at
            self._start = self._write_at if self._overlapping else 0
        else:
            first_part_size = self.maxlen - self._write_at
            first_part = to_add[:first_part_size]
            second_part = to_add[first_part_size:]
            self._ringbuffer[self._write_at:] = first_part
            self._ringbuffer[:len(second_part)] = second_part
            self._write_at = len(second_part)
            self._length = self.maxlen
            self._start = self._write_at
            self._overlapping = True

    def read_last(self, n_samples):
        return self.to_array()[-n_samples:]


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
        self.stream = None
        self.play_thread = None
        self._playback_quit_signal = None
        self._playback_lock = threading.Lock()

        if is_mic:
            self.rec_stream = None
            self.record_buffer = RingBuffer()
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

        self.stream = self.pa.open(
           format=self.pa.get_format_from_width(wf.getsampwidth()),
           channels=wf.getnchannels(),
           rate=wf.getframerate(),
           output=True,
           frames_per_buffer=chunk,
           output_device_index=self.device_index,
        )

        data = wf.readframes(chunk)

        while data != b"":
            if quit_signal.is_set() or abort_signal.is_set():
                logger.debug("Attempting to close pyaudio stream on interrupt")
                self.stream.close()
                self._playback_lock.release()
                logger.debug("Stream closed")
                break

            dtype, max_val = self._get_dtype(wf)
            data = np.frombuffer(data, dtype)

            if self.gain:
                data = data * np.power(10.0, self.gain / 20.0)

            data = data.astype(dtype).tostring()
            self.stream.write(data)
            data = wf.readframes(chunk)
        else:  # This block is run when the while condition becomes False (not on break)
            logger.debug("Attempting to close pyaudio stream on file complete")
            self._playback_lock.release()
            logger.debug("Stream closed")

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

        self.play_thread = threading.Thread(
            target=self._run_play,
            kwargs={
                "wf": self.wf,
                "quit_signal": new_quit_signal,
                "abort_signal": self.abort_signal
            }
        )

        if start:
            self._play_wav(event=event)

        self.wf = None

        return new_quit_signal

    def rec_callback(self, in_data, frame_count, time_info, status):
        data = np.frombuffer(in_data, dtype=np.int16)
        self.record_buffer.extend(data)
        return in_data, pyaudio.paContinue

    def listen(self):
        """Start microphone recording stream
        """
        self.rec_stream = self.pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.rate,
            input_device_index=self.device_index,
            input=True,
            output=False,
            frames_per_buffer=REC_CHUNK,
            stream_callback=self.rec_callback
        )

        # Set up buffer to store last 10 seconds of audio at all times
        self.record_buffer = RingBuffer(int(self.rate) * 20)

    def _get_last_recorded_data(self, duration):
        """Get last few seconds of recorded audio input from mic buffer"""
        n_samples = int(duration * self.rate)
        return self.record_buffer.read_last(n_samples), self.rate

    def _queue_wav(self, wav_file, start=False, event=None, **kwargs):
        if self._playback_quit_signal:
            self._playback_quit_signal.set()

        # We must wait for the previous stream to be closed
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
