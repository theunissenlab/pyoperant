
#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK
import os
import glob
import sys
import tempfile
import traceback
import warnings
import webbrowser

import click


box_required = [
    click.option("-b", "--box", required=True),
]


try:
    import colorama
except ImportError:
    colorama = None
else:
    colorama.init()


class CLIResult:
    @staticmethod
    def fail(s):
        if colorama:
            print("{}...FAILURE{}: {}".format(colorama.Fore.RED, colorama.Style.RESET_ALL, s))
        else:
            print("...FAILURE: {}".format(s))

    @staticmethod
    def warn(s):
        if colorama:
            print("{}...WARNING{}: {}".format(colorama.Fore.ORANGE, colorama.Style.RESET_ALL, s))
        else:
            print("...WARNING: {}".format(s))

    @staticmethod
    def success(s):
        if colorama:
            print("{}...SUCCESS{}: {}".format(colorama.Fore.GREEN, colorama.Style.RESET_ALL, s))
        else:
            print("...SUCCESS: {}".format(s))


def add_options(options):
    def _add_options(func):
        for option in reversed(options):
            func = option(func)
        return func
    return _add_options


@click.group()
def cli():
    pass


@click.command(help="Test box's audio output")
@add_options(box_required)
@click.option("-f", "--file", "file_", type=click.Path(exists=True, dir_okay=False),
        help="path to sound file")
@click.option("--repeat/--no-repeat", default=False, help="loop audio playback")
def test_audio(box, file_, repeat):
    from pyoperant.tlab.tlab_commands import test_audio

    click.echo("Testing audio on box {} with {}".format(box, file_))
    test_audio(box, file_, repeat)


@click.command(help="Test box's microphone recording")
@add_options(box_required)
@click.option("-d", "--duration", type=float, help="time to record for")
@click.option("--playback/--no-playback", default=True, help="play audio from speakers")
def test_microphone(box, duration, playback):
    from pyoperant.tlab.tlab_commands import test_microphone

    click.echo("Testing microphone on box {}".format(box))
    with tempfile.TemporaryDirectory() as tempdir:
        dest = os.path.join(tempdir, "box{}_mic_test.wav".format(box))
        click.echo("...saving output to {}".format(dest))
        test_microphone(box, play_audio=playback, duration=duration, dest=dest)


@click.command(help="Test box button, light, and feeder operation")
@add_options(box_required)
@click.option("-f", "--file", "file_", type=click.Path(exists=True, dir_okay=False),
        help="path to sound file")
def test_box(box, file_):
    from pyoperant.tlab.tlab_commands import test_box
    test_box(box, file_)


@click.command(help="Calibrate pecking key")
@add_options(box_required)
def calibrate_key(box):
    from pyoperant.tlab.tlab_commands import calibrate_box
    calibrate_box(box)


@click.command(help="Read config parameters")
@add_options(box_required)
def read_config(box):
    from pyoperant.tlab.tlab_commands import get_config
    get_config(box)


@click.command(help="Opens config files in Atom for editing")
@click.option("-b", "--box", help="box to edit config for", default="")
def edit_config(box):
    import subprocess
    from pyoperant.tlab.tlab_commands import get_default_config
    if not box:
        from pyoperant.tlab.local_tlab import PANELS
        boxes = list(PANELS.keys())
    else:
        boxes = [box]

    config_files = []
    for box in boxes:
        default_config_file = get_default_config(box)
        print("Opening config file: {}".format(default_config_file))
        config_files.append(default_config_file)

    subprocess.call([
        "atom",
        "-n",
    ] + config_files)


@click.command(help="Run the pecking test on specific box")
@add_options(box_required)
@click.option("-c", "--config", type=click.Path(dir_okay=False), help="override default yaml config file")
@click.option("-s", "--subject", help="override config file subject name")
@click.option("-e", "--experimenter", help="override config file experimenter name")
@click.option("-p/ ", "--preference/--no-preference", "preference_test",
        default=False, help="run preference test (default=False)")
@click.option("--output-dir", help="override data output directory")
def run(box, config, subject, experimenter, preference_test, output_dir):
    """Loads config and runs the main pecking test
    """
    from pyoperant.tlab.tlab_commands import run
    run(
        box,
        config,
        subject,
        experimenter,
        preference_test,
        output_dir
    )


@click.command(help="Launch an IPython shell with boxes imported")
@click.option("-b", "--box", default=None)
def shell(box):
    try:
        from pyoperant.tlab.local_tlab import launch_shell
    except ImportError:
        warnings.warning("Failed to import PANELS from pyoperant.tlab.local_tlab")
        PANELS = {}
    launch_shell(box)


@click.command("diagnostics", help="Run diagnostics for debugging audio/hardware on box")
@click.option("-b", "--box", help="box to diagnose",
        prompt="Select box (leave blank for general diagnostics)", default="")
@click.option("-f", "--file", "file_", type=click.Path(exists=True, dir_okay=False), help="path to sound file to test")
@click.option("-r/ ", "--raise/--no-raise", "raise_", default=False, help="raise exception on caught errors")
def diagnostics(box, file_, raise_):
    """Runs diagnostic tests for one or all boxes, including hardware, config, software
    """
    click.echo()
    click.echo("Checking paths...")
    path = os.environ["PATH"]
    pythonpath = os.environ["PYTHONPATH"]
    syspath = sys.path
    click.echo("PYTHONPATH={}".format(pythonpath))
    click.echo("PATH={}".format(path))
    click.echo("sys.path={}".format(syspath))

    click.echo()
    click.echo("Importing experiment classes...")
    base_imports_failed = False
    try:
        from pyoperant.interfaces.pyaudio_ import list_audio_devices
        from pyoperant.tlab.pecking_test import PeckingTest, PeckingAndPlaybackTest
    except ImportError:
        CLIResult.fail("to import pyoperant packages")
        traceback.print_exc()
        base_imports_failed = True
    else:
        pass

    if base_imports_failed:
        click.echo("A core import failed (see above). Aborting.")
        if "pyoperant" not in syspath:
            click.echo("Pyoperant code directory is not in your python paths")
        click.exit(0)

    if box == "":
        click.echo("Running diagnostics on all boxes")
        box_nums = [2, 3, 5, 6]
        box_names = ["Box{}".format(num) for num in box_nums]
    else:
        click.echo("Running diagnostics on box {}".format(box))
        box_nums = [box]
        box_names = ["Box{}".format(box)]

    # Importing boxes
    import importlib
    click.echo()
    click.echo("Importing Boxes...")
    try:
        local_tlab = importlib.import_module("pyoperant.tlab.local_tlab")
    except ImportError:
        CLIResult.fail("to import Boxes from pyoperant")
        traceback.print_exc()
    else:
        CLIResult.success("boxes imported from pyoperant.tlab.local_tlab")
        box_classes = [getattr(local_tlab, name) for name in box_names]

    # Checking for webcam devices
    click.echo()
    click.echo("Looking for webcams...")
    for num in box_nums:
        webcam_dev = "/dev/video_box{}".format(num)
        if not os.path.exists(webcam_dev):
            CLIResult.fail("{} not found for box {}".format(webcam_dev, num))
        else:
            CLIResult.success("{} located for box {}".format(webcam_dev, num))

    # Checking for audio devices
    click.echo()
    click.echo("Looking for audio interface...")
    import subprocess
    aplay = subprocess.check_output(("aplay", "-L"))
    if not aplay.find(b"surround40:U192k"):
        CLIResult.fail("surround40:U192k device (splits into speaker2-speaker6) not found in 'aplay -L'. Is the audio interface plugged in?")
    else:
        CLIResult.success("found audio output surround40:U192k")

    if not aplay.find(b"hw:U192k"):
        CLIResult.fail("hw:U192k device (splits into mic2-mic6) not found in 'aplay -L'. Is the audio interface plugged in?")
    else:
        CLIResult.success("found audio input hw:U192k")

    # chekcing arduinos
    click.echo()
    click.echo("Looking for arduinos in /dev...")
    for box in box_classes:
        arduino_dev = box.defaults["arduino"]
        if not os.path.exists(arduino_dev):
            CLIResult.fail("{} not found for {}".format(arduino_dev, box))
        else:
            CLIResult.success("{} located for {}".format(arduino_dev, box))

    #Instantiating boxes
    click.echo()
    click.echo("Instantiating Boxes...")
    boxes_failed = []
    boxes_succeeded = []
    for Box in box_classes:
        try:
            b = Box()
        except:
            CLIResult.fail("to instantiate {}".format(Box))
            traceback.print_exc()
            boxes_failed.append(Box)
        else:
            boxes_succeeded.append(b)
            CLIResult.success("instantiated {}".format(Box))

    click.echo()
    if len(boxes_failed):
        CLIResult.fail("{} failed to instantiate. Check speakers and microphones".format(boxes_failed))
        # TODO: add more help with this?
        # os.system("cat /proc/asound/cards",)
        # audio_devices = pa.get_device_info_by_index(0)
        # audio_devices = list_audio_devices()

    click.echo()
    click.echo("Device check complete")
    click.echo("Checking configuration files...")

    for num in box_nums:
        click.echo()
        diagnose_config(num)

    click.echo()

    if click.confirm("Configuration check complete. Proceed to interactive box components tests?"):
        # Flash lights
        for failed_box in boxes_failed:
            click.echo("Skipping {} (failed to instantiate)".format(failed_box.__name__))

        with tempfile.TemporaryDirectory() as tempdir:
            for box in boxes_succeeded:
                click.echo()
                click.echo("Testing box {}".format(box))
                box.test(filename=file_)

                mic_dest = os.path.join(tempdir, "{}_mic_test.wav".format(type(box).__name__))
                click.echo("Testing microphone on box {}".format(box))
                output = box.test_mic_recording(play_audio=True, duration=0.0, dest=mic_dest)

            click.echo()
            click.prompt("Microphone tests complete. Check or copy wav files in {} before proceeding (y to proceed)".format(tempdir))

        for box in boxes_succeeded:
            click.echo("Checking poll rate of box {}".format(box))
            _, mean_rate = box.check_poll_rate(iters=5, duration=1)
            click.echo("Polled from peck port at {:.2f}/s".format(mean_rate))

    click.echo("Diagnostics completed")


def diagnose_config(box):
    """Step through box's config file and report errors"""
    from pyoperant.tlab.tlab_commands import get_default_config, load_config

    default_config_file = get_default_config(box)

    print("Checking default config {} for box {}...".format(default_config_file, box))
    if not os.path.exists(default_config_file):
        CLIResult.fail("config file {} not found".format(default_config_file))
        return
    else:
        CLIResult.success("config file {} located".format(default_config_file))

    try:
        parameters = load_config(default_config_file)
    except:
        CLIResult.fail("failed to read config file {}".format(default_config_file))
        traceback.print_exc()
        return

    # Check base experiment path
    experiment_path = parameters["experiment_path"]
    if not os.path.exists(experiment_path):
        CLIResult.warning("base experiment path {} not found, will be created".format(experiment_path))
    else:
        CLIResult.success("base experiment path {} was found".format(experiment_path))

    # Check stim directory
    stim_directory = parameters["stim_directory"]
    if not os.path.exists(stim_directory):
        CLIResult.fail("stim directory {} not found".format(stim_directory))
    else:
        CLIResult.success("stim directory {} was found".format(stim_directory))

    # Check stim directories exist for all conditions
    conditions = parameters["conditions"]
    keys = list(conditions.keys())
    if "playback" not in conditions:
        CLIResult.warn("'playback' not found in config 'conditions' section (Found {})."
                " Will not be able to run preference tests".format(keys))
    else:
        playback_condition = conditions["playback"][0]
        stim_directory = playback_condition.file_path
        if not os.path.exists(stim_directory):
            CLIResult.fail("playback directory {} not found".format(stim_directory))
        elif not len(glob.glob(os.path.join(stim_directory, "*.wav"))):
            CLIResult.fail("playback directory {} has no wav files".format(stim_directory))
        else:
            CLIResult.success("all playback directories found")

    if "pecking" not in conditions:
        CLIResult.fail("'pecking' not found in config 'conditions' section (Found {}).".format(keys))
    elif len(conditions["pecking"]) != 2:
        CLIResult.fail("conditions->pecking must be len 2 (rewarded and nonrewarded), but got {}".format(conditions["pecking"]))
    else:
        rewarded_condition = conditions["pecking"][0]
        nonrewarded_condition = conditions["pecking"][1]
        rewarded_dir = rewarded_condition.file_path
        nonrewarded_dir = nonrewarded_condition.file_path

        if not os.path.exists(rewarded_dir):
            CLIResult.fail("rewarded stim directory {} not found".format(rewarded_dir))
        elif not len(glob.glob(os.path.join(rewarded_dir, "*.wav"))):
            CLIResult.fail("rewarded stim directory {} has no wav files".format(rewarded_dir))
        else:
            CLIResult.success("rewarded stim directory")

        if not os.path.exists(nonrewarded_dir):
            CLIResult.fail("nonrewarded stim directory {} not found".format(nonrewarded_dir))
        elif not len(glob.glob(os.path.join(nonrewarded_dir, "*.wav"))):
            CLIResult.fail("nonrewarded stim directory {} has no wav files".format(nonrewarded_dir))
        else:
            CLIResult.success("nonrewarded stim directory")

    print()
    print("Validate other parameters on box {}:".format(box))
    print("\n\tsubject_name: {subject_name}\n\tqueue_parameters: {queue_parameters}\n\trecord_audio: {record_audio}\n\t"
            "reward_value: {reward_value}\n\tinactivity_before_playback: {inactivity_before_playback}\n\t"
            "inactivity_before_playback_restart: {inactivity_before_playback_restart}\n\tgain: {gain}".format(**parameters))


cli.add_command(shell)
cli.add_command(diagnostics)
cli.add_command(calibrate_key)
cli.add_command(run)
cli.add_command(test_audio)
cli.add_command(test_microphone)
cli.add_command(read_config)
cli.add_command(edit_config)


if __name__ == "__main__":
    cli()
