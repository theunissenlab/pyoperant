import datetime as dt
import os
import logging
import argparse
from functools import wraps

from pyoperant import hwio, components, panels, utils, InterfaceError, events
from pyoperant.interfaces import nidaq_, pyaudio_, tkgui_

logger = logging.getLogger(__name__)

class Panel131(panels.BasePanel):
    """ The chronic recordings box in room 131

    The speaker should probably be the address of the nidaq card

    Parameters
    ----------
    name: string
        Name of this box
    speaker: string
        Speaker device name for this box
    channel: string
        The channel name for the analog output
    input_channel: string
        The channel name for a boolean input (e.g. perch or peck-port)
        Default None means no input configured

    Attributes
    ----------

    Examples
    --------
    """

    _default_sound_file = "C:/DATA/stimuli/stim_test/1.wav"

    def __init__(self, speaker="Dev1", channel="ao0", mic=None, use_nidaq=True, input_channel=None, name=None, *args, **kwargs):
        super(Panel131, self).__init__(self, *args, **kwargs)
        self.name = name

        # Initialize interfaces
        if use_nidaq:
            speaker_out = nidaq_.NIDAQmxAudioInterface(device_name=speaker,
                                                   clock_channel="/Dev1/PFI0")
        else:
            speaker_out = pyaudio_.PyAudioInterface(device_name=speaker)

        # Create a digital to analog event handler
        analog_event_handler = events.EventDToAHandler(channel=speaker + "/" + "ao1",
                                                       scaling=3.3,
                                                       metadata_bytes=40)
        # Create an audio output
        audio_out = hwio.AudioOutput(interface=speaker_out,
                                     params={"channel": speaker + "/" + channel,
                                             "analog_event_handler": analog_event_handler})

        self.mic = None
        if mic is not None:
            self.mic_rate = 44100
            mic_in = pyaudio_.PyAudioInterface(device_name=mic, input_rate=self.mic_rate)
            audio_in = hwio.AudioInput(interface=mic_in)
            self.mic = components.Microphone(audio_in)
        else:
            self.mic = None

        # Add boolean hwios to inputs and outputs
        self.inputs = []
        self.outputs = [audio_out]

        # Set up components
        self.speaker = components.Speaker(output=audio_out)

        if input_channel is not None:
            boolean_input = hwio.BooleanInput(name="Button",
                                              interface=speaker_out,
                                              params={"channel": speaker + "/" + input_channel,
                                                      "invert": True})
            self.inputs.append(boolean_input)
            self.button = components.Button(IR=boolean_input)

    def reset(self):
        if self.mic:
            self.mic.input.interface.close()

    def sleep(self):
        if self.mic:
            self.mic.input.interface.close()

    def ready(self):

        pass

    def idle(self):

        pass

    def poll_then_sound(self, timeout=None):

        if not hasattr(self, "button"):
            raise AttributeError("This panel does not have a button")

        self.speaker.queue(self._default_sound_file)
        self.button.poll(timeout=timeout)
        self.speaker.play()


class PanelWithInput(Panel131):

    def __init__(self, *args, **kwargs):

        super(PanelWithInput, self).__init__(name="Panel with input",
                                             input_channel="port0/line5")


class Panel131GUI(Panel131):
    def __init__(self, *args, **kwargs):
        super(Panel131GUI, self).__init__(*args, **kwargs)

        self.state = {}
        self.gui = tkgui_.TkInterface(self.state)

        condition_input = hwio.NonBooleanInput(name="condition", interface=self.gui, params={"key": "condition"})
        self.inputs.append(condition_input)
        self.condition_button = components.Button(IR=condition_input)

        stim_input = hwio.NonBooleanInput(name="stim", interface=self.gui, params={"key": "selected_stim"})
        self.inputs.append(stim_input)
        self.stimulus_select = components.Button(IR=stim_input)

        pause_input = hwio.BooleanInput(name="pause", interface=self.gui, params={"key": "paused"})
        self.inputs.append(pause_input)
        self.pause_button = components.Button(IR=pause_input)

        quit_button = hwio.BooleanInput(name="quit", interface=self.gui, params={"key": "quit"})
        self.inputs.append(quit_button)
        self.quit_button = components.Button(IR=quit_button)

        play_input = hwio.BooleanInput(name="play", interface=self.gui, params={"key": "play"})
        self.inputs.append(play_input)
        self.play_button = components.Button(IR=play_input)

class PanelSeewiesen(panels.BasePanel):
    """ The chronic recordings set up for Seewiesen

    The speaker should probably be the address of the nidaq card

    Parameters
    ----------
    name: string
        Name of this box
    speaker: string
        Speaker device name for this box
    channel: string
        The channel name for the analog output
    input_channel: string
        The channel name for a boolean input (e.g. perch or peck-port)
        Default None means no input configured

    Attributes
    ----------

    Examples
    --------
    """

    _default_sound_file = "C:/DATA/stimuli/stim_test/1.wav"

    def __init__(self, speaker="Speakers / Headphones (Realtek ", mic = None, channel="ao0", input_channel=None, name=None, *args, **kwargs):
        super(PanelSeewiesen, self).__init__(self, *args, **kwargs)
        self.name = name

        # Initialize interfaces
        #speaker_out = nidaq_.NIDAQmxAudioInterface(device_name=speaker,
        #                                           clock_channel="/Dev1/PFI0")
        speaker_out = pyaudio_.PyAudioInterface(device_name=speaker)
        # Create a digital to analog event handler
        #analog_event_handler = events.EventDToAHandler(channel=speaker + "/" + "ao1",
        #                                               scaling=3.3,
        #                                               metadata_bytes=40)
        # Create an audio output
        audio_out = hwio.AudioOutput(interface=speaker_out)
        #                             params={"channel": speaker + "/" + channel,
        #                                     "analog_event_handler": analog_event_handler})
        self.mic = None
        if mic is not None:
            self.mic_rate = 44100
            mic_in = pyaudio_.PyAudioInterface(device_name=mic, input_rate=self.mic_rate)
            audio_in = hwio.AudioInput(interface=mic_in)
            self.mic = components.Microphone(audio_in)
        else:
            self.mic = None

        # Add boolean hwios to inputs and outputs
        self.inputs = []
        self.outputs = [audio_out]

        # Set up components
        self.speaker = components.Speaker(output=audio_out)

        if input_channel is not None:
            boolean_input = hwio.BooleanInput(name="Button",
                                              interface=speaker_out,
                                              params={"channel": speaker + "/" + input_channel,
                                                      "invert": True})
            self.inputs.append(boolean_input)
            self.button = components.Button(IR=boolean_input)

    def reset(self):

        pass

    def sleep(self):

        pass

    def ready(self):

        pass

    def idle(self):

        pass

    def poll_then_sound(self, timeout=None):

        if not hasattr(self, "button"):
            raise AttributeError("This panel does not have a button")

        self.speaker.queue(self._default_sound_file)
        self.button.poll(timeout=timeout)
        self.speaker.play()

class PanelSeewiesenInput(PanelSeewiesen):

    def __init__(self, *args, **kwargs):

        super(PanelWithInput, self).__init__(name="Panel with input",
                                             input_channel="port0/line5")


class PanelSeewiesenGUI(PanelSeewiesen):
    def __init__(self, *args, **kwargs):
        super(PanelSeewiesenGUI, self).__init__(*args, **kwargs)

        self.state = {}
        self.gui = tkgui_.TkInterface(self.state)

        condition_input = hwio.NonBooleanInput(name="condition", interface=self.gui, params={"key": "condition"})
        self.inputs.append(condition_input)
        self.condition_button = components.Button(IR=condition_input)

        stim_input = hwio.NonBooleanInput(name="stim", interface=self.gui, params={"key": "selected_stim"})
        self.inputs.append(stim_input)
        self.stimulus_select = components.Button(IR=stim_input)

        pause_input = hwio.BooleanInput(name="pause", interface=self.gui, params={"key": "paused"})
        self.inputs.append(pause_input)
        self.pause_button = components.Button(IR=pause_input)

        quit_button = hwio.BooleanInput(name="quit", interface=self.gui, params={"key": "quit"})
        self.inputs.append(quit_button)
        self.quit_button = components.Button(IR=quit_button)

        play_input = hwio.BooleanInput(name="play", interface=self.gui, params={"key": "play"})
        self.inputs.append(play_input)
        self.play_button = components.Button(IR=play_input)
