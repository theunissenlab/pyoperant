import datetime as dt
import os
import logging
import argparse
from functools import wraps
from unittest import mock

from pyoperant import hwio, components, panels, utils, InterfaceError
from pyoperant.interfaces import pyaudio_, arduino_

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


class Panel125(panels.BasePanel):
    """ One of the boxes in 125 for running the pecking tests

    The arduino is configured with a baud rate of 19200 bits / second. It has an input for the pecking key on channel 4 and outputs for the pecking key, box light, and feeder on channels 8, 9, and 10, respectively.

    The speakers name should probably be "speaker0" or "speaker1" as they are set up to split the headphone out into right and left channels to drive two boxes independently.

    Parameters
    ----------
    name: string
        Name of this box
    arduino: string
        Path to the arduino for this box
    speaker: string
        Speaker device name for this box

    Attributes
    ----------

    Methods
    -------
    test()
    test_audio()
    calibrate()

    Examples
    --------
    """

    _default_sound_file = "/home/fet/test_song.wav"

    def __init__(self, arduino=None, speaker=None, mic=None, name=None, *args, **kwargs):
        super(Panel125, self).__init__(self, *args, **kwargs)
        if arduino is None:
            raise ValueError("Arduino serial port not specified or configured.")
        if speaker is None:
            raise ValueError("Speaker device not specified or configured.")

        self.name = name

        # Initialize interfaces
        arduino = arduino_.ArduinoInterface(device_name=arduino,
                                            baud_rate=19200)
        headphone_out = pyaudio_.PyAudioInterface(device_name=speaker)

        # Create input and output for the pecking key
        button = hwio.BooleanInput(name="Pecking key input",
                                   interface=arduino,
                                   params=dict(channel=4, invert=True, suppress_longpress=True))
        light = hwio.BooleanOutput(name="Pecking key light",
                                   interface=arduino,
                                   params=dict(channel=8))
        # Create an output for the box's main light
        main_light = hwio.BooleanOutput(name="Box light",
                                        interface=arduino,
                                        params=dict(channel=9))
        # Create an output for the feeder
        feeder = hwio.BooleanOutput(name="Feeder",
                                    interface=arduino,
                                    params=dict(channel=10))
        # Create an audio output
        audio_out = hwio.AudioOutput(interface=headphone_out)

        # Create a mic input
        if mic is not None:
            mic_in = pyaudio_.PyAudioInterface(device_name=mic)
            audio_in = hwio.AudioInput(interface=mic_in)
            self.mic = components.Microphone(audio_in)

        # Add boolean hwios to inputs and outputs
        self.inputs = [button]
        self.outputs = [light, main_light, feeder]

        # Set up components
        self.speaker = components.Speaker(output=audio_out)
        self.peck_port = components.PeckPort(IR=button, LED=light)
        self.house_light = components.HouseLight(light=main_light)
        self.feeder = components.Hopper(solenoid=feeder)

        # Translations
        self.response_port = self.peck_port

    def reward(self, value=12.0):
        """Raise feeder for some time"""
        self.feeder.up()
        peck_time = self.peck_port.poll(value)
        self.feeder.down()
        if peck_time is not None:
            return peck_time

        return True

    def punish(self):
        pass

    def reset(self):
        self.peck_port.off()
        self.house_light.on()
        self.feeder.down()

    def sleep(self):
        self.peck_port.off()
        self.house_light.off()
        self.feeder.down()

    def ready(self):
        self.feeder.down()
        self.house_light.on()
        self.peck_port.on()

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


class Box2(Panel125):

    defaults = dict(
        name="Box 2",
        arduino="/dev/ttyArduino_box2",
        speaker="speaker2",
        mic="mic2",
    )

    def __init__(self, *args, **kwargs):
        super(Box2, self).__init__(*args, **{**self.defaults, **kwargs})


class Box3(Panel125):

    defaults = dict(
        name="Box 3",
        arduino="/dev/ttyArduino_box3",
        speaker="speaker3",
        mic="mic3",
    )

    def __init__(self, *args, **kwargs):
        super(Box3, self).__init__(*args, **{**self.defaults, **kwargs})


class Box5(Panel125):

    defaults = dict(
        name="Box 5",
        arduino="/dev/ttyArduino_box5",
        speaker="speaker5",
        mic="mic5",
    )

    def __init__(self, *args, **kwargs):
        super(Box5, self).__init__(*args, **{**self.defaults, **kwargs})


class Box6(Panel125):

    defaults = dict(
        name="Box 6",
        arduino="/dev/ttyArduino_box6",
        speaker="speaker6",
        mic="mic6",
    )

    def __init__(self, *args, **kwargs):
        super(Box6, self).__init__(*args, **{**self.defaults, **kwargs})


class BoxVirtual(Panel125):
    defaults = dict(
        name="Virtual Box",
        arduino="fakearduinoboi",
        speaker="default",
        mic="default",
    )

    # @mock.patch("pyoperant.interfaces.pyaudio_.PyAudioInterface", pyaudio_.MockPyAudioInterface)
    @mock.patch("pyoperant.interfaces.arduino_.ArduinoInterface", arduino_.MockArduinoInterface)
    def __init__(self, *args, **kwargs):
        super(BoxVirtual, self).__init__(*args, **{**self.defaults, **kwargs})


PANELS = {
    "2": Box2,
    "3": Box3,
    "5": Box5,
    "6": Box6,
    # "virtual": BoxVirtual
}


def launch_shell(box=None):
    from IPython import embed

    _boxes = []
    if box and box in PANELS:
        _boxes = [box]
    elif not box:
        _boxes = []

    print("Initialized variable PANELS:\n{}".format(PANELS))
    for _box in _boxes:
        globals()["box{}".format(_box)] = PANELS[_box]()
        print("\nInitialized variable box{}".format(_box))
    print()
    embed(colors="neutral")


def debug_box_audio(args):
    audio_devices = pyaudio_.list_audio_devices()
