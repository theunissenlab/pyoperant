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
        if filename is None:
            filename = self._default_sound_file

        self.reset()

        print("Flashing pecking port")
        self.peck_port.flash(2.0, .1)
        print("Raising feeder")
        self.reward(5.0)

        print("Playing test sound")
        self.speaker.queue(filename)
        self.speaker.play()

        print("Polling for input. Peck to proceed (10 second timeout)")
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
        for ii in xrange(iters):
            print("Iteration %d: " % ii),
            count = 0
            current_time = time.time()
            while True:
                count += 1
                self.peck_port.status()
                if time.time() - current_time > duration:
                    break
            num_polls.append(count)
            print("%d" % count)

        return [float(pc) / duration for pc in num_polls]

    def sound_then_feeder(self, filename="", duration=12, flash=False, flash_dur=3):
        """ Pairs the sound playback with the feeder coming up.
        Hit Ctrl+C to stop the sound or put the feeder down.
        :param filename: path to sound file.
        :param duration: duration the feeder is up (seconds)
        :param flash: whether or not to flash the button at the start (default False)
        """

        if not filename:
            filename = self._default_sound_file
        self.speaker.queue(filename)

        if flash:
            self.peck_port.flash(dur=flash_dur)

        self.speaker.play()
        try:
            while self.speaker.output.interface.stream.is_active():
                utils.wait(0.1)
        except KeyboardInterrupt:
            pass
        finally:
            self.speaker.stop()

        try:
            self.feeder.feed(duration)
        except KeyboardInterrupt:
            self.feeder.down()

    def test_audio(self, filename="", repeat=False):

        if not filename:
            filename = self._default_sound_file

        print("Testing sound playback with %s" % filename)
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


class Box5(Panel125):

    def __init__(self, *args, **kwargs):
        defaults = dict(
            name="Box 5",
            arduino="/dev/ttyArduino_box5",
            speaker="speaker5",
            mic="mic5",
        )
        defaults.update(**kwargs)
        super(Box5, self).__init__(*args, **defaults)


class Box6(Panel125):

    def __init__(self, *args, **kwargs):
        defaults = dict(
            name="Box 6",
            arduino="/dev/ttyArduino_box6",
            speaker="speaker6",
            mic="mic6",
        )
        defaults.update(**kwargs)
        super(Box6, self).__init__(*args, **defaults)


class Box2(Panel125):

    def __init__(self, *args, **kwargs):
        defaults = dict(
            name="Box 2",
            arduino="/dev/ttyArduino_box2",
            speaker="speaker2",
            mic="mic2",
        )
        defaults.update(**kwargs)
        super(Box2, self).__init__(*args, **defaults)


class Box3(Panel125):

    def __init__(self, *args, **kwargs):
        defaults = dict(
            name="Box 3",
            arduino="/dev/ttyArduino_box3",
            speaker="speaker3",
            mic="mic3",
        )
        defaults.update(**kwargs)
        super(Box3, self).__init__(*args, **defaults)


class BoxVirtual(Panel125):

    _default_sound_file = "/home/tlee/code/neosound/data/zbsong.wav"

    @mock.patch("pyoperant.interfaces.pyaudio_.PyAudioInterface", pyaudio_.MockPyAudioInterface)
    @mock.patch("pyoperant.interfaces.arduino_.ArduinoInterface", arduino_.MockArduinoInterface)
    def __init__(self, *args, **kwargs):
        defaults = dict(
            name="Virtual Box",
            arduino="fakearduinoboi",
            speaker="HD-Audio Generic: ALC887-VD Analog (hw:1,0)",
            mic="default",
        )
        defaults.update(**kwargs)
        super(BoxVirtual, self).__init__(
            *args,
            **defaults
        )


class Thing13(Panel125):

    _default_sound_file = "/home/tlee/code/neosound/data/zbsong.wav"

    def __init__(self, *args, **kwargs):
        super(Thing13, self).__init__(name="Tyler Laptop",
                                      arduino="/dev/ttyACM0",
                                      speaker="pulse", *args, **kwargs)


def _identify_box(args):
    if args.box == "virtual":
        Box = BoxVirtual
    else:
        Box = globals()["Box{}".format(args.box)]
    return Box


# Scripting methods
def test_box(args):
    kwargs = dict()
    if args.sound is not None:
        kwargs["filename"] = args.sound

    box = _identify_box(args)()
    box.test(**kwargs)


def test_box_audio(args):

    box = _identify_box(args)()
    kwargs = dict()
    if args.sound is not None:
        kwargs["filename"] = args.sound
    if args.repeat is not None:
        kwargs["repeat"] = args.repeat

    box.test_audio(**kwargs)


def debug_box_audio(args):
    Box = _identify_box(args)
    audio_devices = pyaudio_.list_audio_devices()

    box_kwargs = dict()

    print("\n", "*" * 80)
    print("Debugging audio...")
    print()
    idx = input("""Override speaker?\n{}\n""".format("\n".join(
        ["{}: {}".format(i, name) for i, name in enumerate(audio_devices)]
    )))
    if idx in audio_devices:
        box_kwargs["speaker"] = idx
    else:
        try:
            box_kwargs["speaker"] = audio_devices[int(idx)]
        except:
            pass
    box = Box(**box_kwargs)

    kwargs = dict()
    if args.sound is not None:
        kwargs["filename"] = args.sound
    if args.repeat is not None:
        kwargs["repeat"] = args.repeat

    box.test_audio(**kwargs)
    print("Did the audio come out where it was supposed to?")
    print("Debugging completed. Don't forget to like and subscribe.")


def calibrate_box(args):
    box = _identify_box(args)()
    box.calibrate()


def shutdown_box(args):
    box = _identify_box(args)()
    box.sleep()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run methods associated with a particular box")
    subparsers = parser.add_subparsers(title="methods",
                                       description="Valid methods",
                                       help="Which method to run on the specified box")

    test_parser = subparsers.add_parser("test",
                                        description="Test whether all components of a box are functioning")
    test_parser.add_argument("box", help="Which box to run (e.g. 5) ('virtual' for test)", type=str)
    test_parser.add_argument("-s", "--sound", help="path to sound file to play")
    test_parser.set_defaults(func=test_box)

    # The test_audio script parser
    test_audio_parser = subparsers.add_parser("test_audio",
                                              description="Test just the audio of a box")
    test_audio_parser.add_argument("box", help="Which box to run (e.g. 5) ('virtual' for test)", type=str)
    test_audio_parser.add_argument("-s", "--sound", help="path to sound file to play")
    test_audio_parser.add_argument("--repeat", action="store_true", help="loop the sound")
    test_audio_parser.set_defaults(func=test_box_audio)

    debug_audio_parser = subparsers.add_parser("debug_audio",
                                              description="Assistance in debugging audio issues")
    debug_audio_parser.add_argument("box", help="Which box to run (e.g. 5) ('virtual' for test)", type=str)
    debug_audio_parser.add_argument("-s", "--sound", help="path to sound file to play")
    debug_audio_parser.add_argument("--repeat", action="store_true", help="loop the sound")
    debug_audio_parser.set_defaults(func=debug_box_audio)

    # The calibrate script parser
    calibrate_parser = subparsers.add_parser("calibrate", description="Calibrate the pecking key of a box")
    calibrate_parser.add_argument("box", help="Which box to run (e.g. 5) ('virtual' for test)", type=str)
    calibrate_parser.set_defaults(func=calibrate_box)

    # Shutdown script parser
    shutdown_parser = subparsers.add_parser("shutdown", description="Shutdown a specified box")
    shutdown_parser.add_argument("box", help="Which box to run (e.g. 5) ('virtual' for test)", type=str)
    shutdown_parser.set_defaults(func=shutdown_box)

    args = parser.parse_args()

    args.func(args)
