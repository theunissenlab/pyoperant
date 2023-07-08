import datetime as dt
import os
import logging
import argparse
from functools import wraps
from unittest import mock
from pyoperant.utils import get_object_from_string

from pyoperant import hwio, components, panels, utils, InterfaceError, events
from pyoperant.interfaces import nidaq_, pyaudio_, tkgui_,arduino_

logger = logging.getLogger(__name__)


def shutdown_on_error(func):

    @wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except KeyboardInterrupt:
            print("Shutting down")
            self.sleep()
        except:
            self.sleep()
            raise
    return wrapper

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
            nidaq_device = nidaq_.NIDAQmxInterface(device_name=speaker,
                                                   clock_channel="/Dev1/PFI0")
            speaker_out = nidaq_.NIDAQmxAudioInterface(device=nidaq_device)
            
            # TODO make sure that nidaq can handle event logging
            #event_out = events.EventInterfaceHandler(interface=nidaq_device,params={'channel':'/Dev1/port0/line0'})
            #events.events.add_handler(event_out )
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

class Panel131Operant(panels.BasePanel):
    def __init__(self, arduino="COM5", speaker="Dev1", channel='ao0', use_nidaq=True, mic=None, name=None,
                 baud_rate=115200, *args, **kwargs):
        super(Panel131Operant, self).__init__(self, *args, **kwargs)
        if arduino is None:
            raise ValueError("Arduino Serial Port not specified or configured")
        if speaker is None:
            raise ValueError("Speaker device not specified or configured")
        
        self.name = name
        arduino = arduino_.ArduinoInterface(device_name=arduino,
                                            baud_rate=baud_rate)

         # Initialize interfaces
        if use_nidaq:
            nidaq_device = nidaq_.NIDAQmxInterface(device_name=speaker,
                                                   clock_channel="/Dev1/PFI0")
            speaker_out = nidaq_.NIDAQmxAudioInterface(device=nidaq_device)
            #,
            #                                            clock_channel="/Dev1/PFI0")
            # nidaq_device = nidaq_.NIDAQmxInterface(device_name=speaker,
            #                                        clock_channel="/Dev1/PFI0")
            # speaker_out = nidaq_.NIDAQmxAudioInterface(device=nidaq_device)
            
            # TODO make sure that nidaq can handle event logging
            #event_out = events.EventInterfaceHandler(interface=nidaq_device,params={'channel':'/Dev1/port0/line0'})
            #events.events.add_handler(event_out )
        else:
            speaker_out = pyaudio_.PyAudioInterface(device_name=speaker)

        # Create a digital to analog event handler
        analog_event_handler = events.EventDToAHandler(channel=speaker + "/" + "ao1",
                                                       scaling=3.3,
                                                       metadata_bytes=40)

        # Create input and output for the pecking key
        button = hwio.BooleanInput(name="Pecking key input",
                                   interface=arduino,
                                   params=dict(channel=4, invert=True, suppress_longpress=True))
        light = hwio.BooleanOutput(name="Pecking key light",
                                   interface=arduino,
                                   params=dict(channel=8))
        ttl_input = hwio.BooleanInput(name="TTL", interface=arduino,
                                    params=dict(channel=53))
        # Create an output for the box's main light
        main_light = hwio.BooleanOutput(name="Box light",
                                        interface=arduino,
                                        params=dict(channel=9))
        # Create an output for the feeder
        feeder = hwio.BooleanOutput(name="Feeder",
                                    interface=arduino,
                                    params=dict(channel=10))
        # Create an audio output
        audio_out = hwio.AudioOutput(interface=speaker_out,
                                     params={"channel": speaker + "/" + channel,
                                             "analog_event_handler": analog_event_handler})

        # Add boolean hwios to inputs and outputs
        self.inputs = [button, ttl_input]
        self.outputs = [light, main_light, feeder]

        # Set up components
        self.speaker = components.Speaker(output=audio_out)
        self.peck_port = components.PeckPort(IR=button, LED=light)
        self.house_light = components.HouseLight(light=main_light)
        self.ttl_monitor = components.TTLMonitor(input_=ttl_input)
        self.peck_port.on()
        self.feeder = components.Hopper(solenoid=feeder)

        # Translations
        self.response_port = self.peck_port
    
    def reward(self, value=12.0,and_poll=True):
        if and_poll:
            """Raise feeder for some time"""
            logger.debug("About to call feeder.up()")
            self.feeder.up()
            logger.debug("Called feeder.up()")
            peck_time = self.peck_port.poll(value)
            self.feeder.down()
            if peck_time is not None:
                return peck_time

            return True
        else:
            """Raise feeder for some time"""
            self.response_port.off()
            logger.debug("About to call feeder.up()")
            self.feeder.up()
            logger.debug("Called feeder.up()")
            utils.wait(value)
            self.feeder.down()
            self.response_port.on()
            return True

    def punish(self):
        pass

    def reset(self):
        self.peck_port.off()
        self.house_light.on()
        self.feeder.down()
        self.ttl_monitor.stop()

    def sleep(self):
        self.peck_port.off()
        self.house_light.off()
        self.feeder.down()

    def ready(self):
        self.feeder.down()
        self.house_light.on()
        self.peck_port.on()
        self.ttl_monitor.start()

    def idle(self):
        self.reset()

    @shutdown_on_error
    def test(self, filename=None):
        """Test operation of pecking test box"""
        if filename is None:
            filename = self._default_sound_file

        self.reset()

        print("...flashing pecking port")
        self.peck_port.flash(2.0, .1)
        print("...raising feeder")
        self.reward(5.0)

        print("...playing test audio {}".format(filename))
        self.speaker.queue(filename)
        self.speaker.play()

        print("...polling for input. Peck to proceed (10 second timeout)")
        self.peck_port.poll(10)
        self.speaker.stop()
        self.reset()

    @shutdown_on_error
    def calibrate(self):
        self.peck_port.off()
        while True:
            is_pecked = self.peck_port.status()
            if is_pecked:
                current_time = dt.datetime.now()
                print("%s: Pecked!" % current_time.strftime("%H:%M:%S"))
                self.peck_port.on()
            utils.wait(0.05)
            self.peck_port.off()

    @shutdown_on_error
    def check_poll_rate(self, iters=10, duration=10):
        import time

        num_polls = list()
        for ii in range(iters):
            print("...iteration {}".format(ii))
            count = 0
            current_time = time.time()
            while True:
                count += 1
                self.peck_port.status()
                if time.time() - current_time > duration:
                    break
            num_polls.append(count)

        rates = [float(pc) / duration for pc in num_polls]
        mean_rate = sum(rates) / len(rates)
        return rates, mean_rate

    def test_audio(self, filename="", repeat=False):
        if not filename:
            filename = self._default_sound_file

        while True:
            self.speaker.queue(filename)
            self.speaker.play()

            try:
                self.speaker.let_finish()
            except KeyboardInterrupt:
                return
            finally:
                self.speaker.stop()

            if not repeat:
                break

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

    def __init__(self, speaker="Speakers (2- High Definition Au", mic = None, channel="ao0", input_channel=None, name=None, *args, **kwargs):
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

class PanelSeewiesenNI(panels.BasePanel):
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

    def __init__(self, speaker="Dev1", mic = None, channel="ao0", use_nidaq=True, input_channel=None, name=None, *args, **kwargs):
        super(PanelSeewiesenNI, self).__init__(self, *args, **kwargs)
        self.name = name

        # Initialize interfaces
        if (use_nidaq):
            nidaq_device = nidaq_.NIDAQmxInterface(device_name=speaker,
                                                   clock_channel="/Dev1/PFI0")
            speaker_out = nidaq_.NIDAQmxAudioInterface(device=nidaq_device)
            # Create a digital to analog event handler
            analog_event_handler = events.EventDToAHandler(channel=speaker + "/" + "ao1",
                                                          scaling=3.3,
                                                          metadata_bytes=40)
            # Create a digital event handler
            digital_event_handler = events.EventDigitalHandler(channel= speaker + "/" + "port0", on_off_bit = True, action_bits=4)
            audio_out = hwio.AudioOutput(interface=speaker_out,
                                                 params={"channel": speaker + "/" + channel,
                                                         "analog_event_handler": analog_event_handler,
                                                         "digital_event_handler": digital_event_handler})
        else:
            # To use the PC soundcard instead of NI, call with use_nidaq=False and speaker = "Speakers (2- High Definition Au"
            speaker_out = pyaudio_.PyAudioInterface(device_name=speaker)
            audio_out = hwio.AudioOutput(interface=speaker_out)


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

class PanelSeewiesenInputNI(PanelSeewiesenNI):

    def __init__(self, *args, **kwargs):

        super(PanelSeewiesenInputNI, self).__init__(name="Panel with input",
                                             input_channel="port0/line5")


class PanelSeewiesenGUINI(PanelSeewiesenNI):
    def __init__(self, *args, **kwargs):
        super(PanelSeewiesenGUINI, self).__init__(*args, **kwargs)

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




if __name__ == '__main__':
    # Pecking Test
    from pyoperant import configure
    from pyoperant.tlab.pecking_test import PeckingTest
    c = configure.ConfigureYAML.load("D:\pyoperant\experiments\OperantTemplate\Box131.yaml")
    conditions = c['conditions'].copy()
    conditions_list = []
    for condition_dict in conditions:
        condition = get_object_from_string(condition_dict['class'])
        conditions_list.append(condition(file_path=condition_dict["file_path"]))
    c['conditions'] = conditions_list
    exp = PeckingTest(**c)
    exp.run()
    
    