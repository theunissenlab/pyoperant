import datetime as dt
import os
import logging
import argparse

from pyoperant import hwio, components, panels, utils, InterfaceError
from pyoperant.tlab import components_tlab, hwio_tlab
from pyoperant.interfaces import pyaudio_, arduino_  # , avconv_

logger = logging.getLogger(__name__)

class TLabPanel(panels.BasePanel):

    _default_sound_file = "/home/fet/test_song.wav"

    configuration = {"key_input": 4,
                     "key_light": 8,
                     "main_light": 9,
                     "feeder": 10,
                     }
    baud_rate = 19200

    def __init__(self, configuration, *args, **kwargs):

        super(TLabPanel, self).__init__(self, *args, **kwargs)

        self.configuration = TLabPanel.configuration.copy()
        self.configuration.update(configuration)

        # Initialize interfaces
        self.interfaces['arduino'] = arduino_.ArduinoInterface(device_name=self.configuration['arduino'],
                                                                baud_rate=self.baud_rate)
        for ii in xrange(60):
            try:
                self.interfaces['pyaudio'] = pyaudio_.PyAudioInterface(device_name=self.configuration['speaker'])
                break
            except InterfaceError:
                if ii == 59:
                    raise
                else:
                    utils.wait(1.0)

        # self.interfaces['avconv'] = avconv_.AVConvInterface()

        # Create hardware inputs and outputs
        self.inputs.append(hwio.BooleanInput(name="Pecking key input",
                                             interface=self.interfaces['arduino'],
                                             params={"channel": self.configuration["key_input"],
                                                     "pullup": True}))


        self.outputs.append(hwio.BooleanOutput(name="Pecking key light",
                                               interface=self.interfaces['arduino'],
                                               params={"channel": self.configuration["key_light"]}))
        self.outputs.append(hwio.BooleanOutput(name="Main light",
                                               interface=self.interfaces['arduino'],
                                               params={"channel": self.configuration["main_light"]}))
        self.outputs.append(hwio.BooleanOutput(name="Feeder",
                                               interface=self.interfaces['arduino'],
                                               params={"channel": self.configuration["feeder"]}))


        # Set up components
        self.speaker = hwio.AudioOutput(interface=self.interfaces['pyaudio'])
        # self.camera = hwio.CameraInput(name="Webcam",
        #                                interface=self.interfaces['avconv'],
        #                                params={'video_params':{},
        #                                        'audio_params':{}}))

        self.peck_port = components.PeckPort(IR=self.inputs[0], LED=self.outputs[0])
        self.house_light = components.HouseLight(light=self.outputs[1])
        self.feeder = components_tlab.HopperNoIR(solenoid=self.outputs[2])

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
        for output in self.outputs:
            output.write(False)
        self.house_light.on()
        self.feeder.down()

    def sleep(self):
        for output in self.outputs:
            output.write(False)
        self.house_light.off()
        self.feeder.down()


    def test(self):
        self.reset()

        print("Flashing pecking port")
        self.peck_port.flash(2.0, .1)
        print("Raising feeder")
        self.reward(5.0)

        print("Playing test sound")
        self.speaker.queue(self._default_sound_file)
        self.speaker.play()

        print("Polling for input. Peck to proceed (10 second timeout)")
        self.peck_port.poll(10)
        self.speaker.stop()
        self.reset()
        return True

    def calibrate(self):

        self.peck_port.off()
        try:
            while True:
                is_pecked = self.peck_port.status()
                if is_pecked:
                    current_time = dt.datetime.now()
                    print("%s: Pecked!" % current_time.strftime("%H:%M:%S"))
                    self.peck_port.on()
                utils.wait(0.05)
                self.peck_port.off()
        except KeyboardInterrupt:
            print("Finished calibration")

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

    def test_audio(self, filename="", repeat=False):

        if not filename:
            filename = self._default_sound_file

        print("Testing sound playback with %s" % filename)
        while True:
            self.speaker.queue(filename)
            self.speaker.play()

            try:
                while self.speaker.interface.stream.is_active():
                    utils.wait(0.1)
            except KeyboardInterrupt:
                return
            finally:
                self.speaker.stop()

            if not repeat:
                break

    def ready(self):

        self.peck_port.on()

    def idle(self):

        self.peck_port.off()


class Thing1(TLabPanel):

    configuration = {"arduino": "/dev/ttyACM0",
                     "speaker": "speaker0"}

    def __init__(self, *args, **kwargs):

        super(Thing1, self).__init__(self.configuration, *args, **kwargs)


class Thing2(TLabPanel):

    configuration = {"arduino": "/dev/ttyUSB0",
                     "speaker": "default"}

    def __init__(self, *args, **kwargs):

        super(Thing2, self).__init__(self.configuration, *args, **kwargs)

class Box5(TLabPanel):
    # /dev/ttyACM0
    configuration = {"arduino": "/dev/ttyArduino_box5",
                     "speaker": "speaker0"}

    def __init__(self, *args, **kwargs):
        super(Box5, self).__init__(self.configuration, *args, **kwargs)


class Box6(TLabPanel):
    # /dev/ttyACM1
    configuration = {"arduino": "/dev/ttyArduino_box6",
                     "speaker": "speaker1"}

    def __init__(self, *args, **kwargs):
        super(Box6, self).__init__(self.configuration, *args, **kwargs)


class Box2(TLabPanel):
    #/dev/ttyACM0
    configuration = {"arduino": "/dev/ttyArduino_box2",
                     "speaker": "speaker1"}

    def __init__(self, *args, **kwargs):
        super(Box2, self).__init__(self.configuration, *args, **kwargs)


class Box3(TLabPanel):

    configuration = {"arduino": "/dev/ttyArduino_box3",
                     "speaker": "speaker0"}

    def __init__(self, *args, **kwargs):
        super(Box3, self).__init__(self.configuration, *args, **kwargs)


class Mac(TLabPanel):

    configuration = {"arduino": "/dev/tty.usbserial-A700619q",
                     "speaker": "Built-in Output"}

    def __init__(self, *args, **kwargs):
        super(Mac, self).__init__(self.configuration, *args, **kwargs)


# Scripting methods
def test_box(args):

    box = globals()["Box%d" % args.box]()
    box.test()


def test_box_audio(args):

    box = globals()["Box%d" % args.box]()
    kwargs = dict()
    if args.sound is not None:
        kwargs["filename"] = args.sound
    if args.repeat is not None:
        kwargs["repeat"] = args.repeat

    box.test_audio(**kwargs)


def calibrate_box(args):

    box = globals()["Box%d" % args.box]()
    box.calibrate()

def shutdown_box(args):

    box = globals()["Box%d" % args.box]()
    box.sleep()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run methods associated with a particular box")
    subparsers = parser.add_subparsers(title="methods",
                                       description="Valid methods",
                                       help="Which method to run on the specified box")

    test_parser = subparsers.add_parser("test",
                                        description="Test whether all components of a box are functioning")
    test_parser.add_argument("box", help="Which box to run (e.g. 5)", type=int)
    test_parser.add_argument("-s", "--sound", help="path to sound file to play")
    test_parser.set_defaults(func=test_box)

    # The test_audio script parser
    test_audio_parser = subparsers.add_parser("test_audio",
                                              description="Test just the audio of a box")
    test_audio_parser.add_argument("box", help="Which box to run (e.g. 5)", type=int)
    test_audio_parser.add_argument("-s", "--sound", help="path to sound file to play")
    test_audio_parser.add_argument("--repeat", action="store_true", help="loop the sound")
    test_audio_parser.set_defaults(func=test_box_audio)

    # The calibrate script parser
    calibrate_parser = subparsers.add_parser("calibrate", description="Calibrate the pecking key of a box")
    calibrate_parser.add_argument("box", help="Which box to run (e.g. 5)", type=int)
    calibrate_parser.set_defaults(func=calibrate_box)

    # Shutdown script parser
    shutdown_parser = subparsers.add_parser("shutdown", description="Shutdown a specified box")
    shutdown_parser.add_argument("box", help="Which box to run (e.g. 5)", type=int)
    shutdown_parser.set_defaults(func=shutdown_box)


    args = parser.parse_args()
    args.func(args)