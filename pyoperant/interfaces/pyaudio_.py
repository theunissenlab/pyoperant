import pyaudio
import wave
import logging
from pyoperant.interfaces import base_
from pyoperant import InterfaceError
from pyoperant.events import events

logger = logging.getLogger(__name__)
# TODO: Clean up _stop_wav logging changes

class PyAudioInterface(base_.AudioInterface):
    """Class which holds information about an audio device

    assign a simple callback function that will execute on each frame
    presentation by writing interface.callback

    interface.callback() should return either True (to continue playback) or
    False (to terminate playback)

    Before assigning any callback function, please read the following:
    https://www.assembla.com/spaces/portaudio/wiki/Tips_Callbacks

    """
    def __init__(self,device_name='default',*args,**kwargs):
        super(PyAudioInterface, self).__init__(*args,**kwargs)
        self.device_name = device_name
        self.device_index = None
        self.stream = None
        self.wf = None
        self.callback = None
        self.open()

    def open(self):
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
        try:
            self.stream.close()
        except AttributeError:
            self.stream = None
        try:
            self.wf.close()
        except AttributeError:
            self.wf = None
        self.pa.terminate()

    def _get_stream(self, start=False, event=None):
        """
        """
        def _callback(in_data, frame_count, time_info, status):
            try:
                cont = self.callback()
            except TypeError:
                cont = True

            if cont:
                data = self.wf.readframes(frame_count)
                return (data, pyaudio.paContinue)
            else:
                return (0, pyaudio.paComplete)

        self.stream = self.pa.open(format=self.pa.get_format_from_width(self.wf.getsampwidth()),
                                   channels=self.wf.getnchannels(),
                                   rate=self.wf.getframerate(),
                                   output=True,
                                   output_device_index=self.device_index,
                                   start=False,
                                   stream_callback=_callback)
        if start:
            self._play_wav(event=event)

    def _queue_wav(self, wav_file, start=False, event=None):
        logger.debug("Queueing wavfile %s" % wav_file)
        self.wf = wave.open(wav_file)
        self.validate()
        self._get_stream(start=start, event=event)

    def _play_wav(self, event=None):
        logger.debug("Playing wavfile")
        events.write(event)
        self.stream.start_stream()

    def _stop_wav(self, event=None):
        try:
            logger.debug("Attempting to close pyaudio stream")
            events.write(event)
            self.stream.close()
            logger.debug("Stream closed")
        except AttributeError:
            self.stream = None
        try:
            self.wf.close()
        except AttributeError:
            self.wf = None
