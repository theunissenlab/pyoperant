# Scripting commands for operating pecking boxes
# and command line operation
import datetime
import os

from pyoperant import configure


# Set up default directories
HOME_DIR = os.path.abspath(os.path.expanduser("~"))
stimuli_dir = os.path.join(HOME_DIR, "stimuli")
config_dir = os.path.join(HOME_DIR, "configs")
data_dir = os.path.join(HOME_DIR, "data")


def get_default_config(box):
    return os.path.join(config_dir, "Box{box}.yaml".format(box=box))


def load_config(config_file):
    if config_file.lower().endswith(".json"):
        parameters = configure.ConfigureJSON.load(config_file)
    elif config_file.lower().endswith(".yaml"):
        parameters = configure.ConfigureYAML.load(config_file)
    else:
        raise ValueError("Currently only .yaml and .json configuration files are allowed")

    return parameters


def get_daily_experiment_path(base_experiment_path, subject_name, date):
    return os.path.join(base_experiment_path, subject_name, date.strftime("%d%m%y"))


def test_box(box, file_=None):
    from pyoperant.tlab.local_tlab import PANELS
    Box = PANELS.get(box)
    box = Box()
    box.test(filename=file_)


def test_audio(box, file_=None, repeat=False):
    from pyoperant.tlab.local_tlab import PANELS
    Box = PANELS.get(box)
    box = Box()
    box.test_audio(filename=file_, repeat=repeat)


def shell(box):
    """Launch an ipython shell that automatically initializes boxes"""
    from pyoperant.tlab.local_tlab import launch_shell
    launch_shell(box)


def calibate_box(box):
    from pyoperant.tlab.local_tlab import PANELS
    Box = PANELS.get(box)
    box = Box()
    box.calibrate()


def get_config(box):
    import pprint
    default_config_file = get_default_config(box)
    print("Loading config file: {}".format(default_config_file))
    parameters = load_config(default_config_file)
    pprint.pprint(parameters)


def run(
        box,
        config,
        subject,
        experimenter,
        preference_test,
        output_dir
    ):
    """Loads config, sets up data locations, and runs the pecking test

    For an experiment on DATE,

    1. Creates a folder at output_dir/subject/DATE that
        will contain the csv, logfiles and audio recordings
        generated during the experiment.
    2. Creates a symlink from ~/data_Box{BOX} to the folder
        output_dir/subject/DATE
    """
    from pyoperant.tlab.local_tlab import PANELS
    from pyoperant.tlab.pecking_test import (
        PeckingAndPlaybackTest,
        PeckingTest
    )

    box_name = PANELS[box].__name__

    config_file = get_default_config(box)

    # Find the config file if default is overriden by command line option
    if config:
        if os.path.exists(config):
            config_file = config
        elif os.path.exists(os.path.join(config_dir, config)):
            config_file = os.path.join(config_dir, config)
        else:
            raise IOError("Config file {} not found".format(config or config_file))

    # Parse the config file
    parameters = load_config(config_file)

    # Override parameters with command line options
    if subject:
        parameters["subject_name"] = subject
    if experimenter:
        parameters["experimenter"]["name"] = experimenter
    if output_dir:
        parameters["experiment_path"] = output_dir

    # Create an output directory with the subject name and today's date
    parameters["experiment_path"] = get_daily_experiment_path(
        parameters["experiment_path"],
        parameters["subject_name"],
        datetime.date.today()
    )

    if not os.path.exists(parameters["experiment_path"]):
        os.makedirs(parameters["experiment_path"])

    # Set up a symlink in the home directory from data_Box{BOX} -> {experiment_path}/{subject}/{date}
    data_link = os.path.expanduser(os.path.join("~", "data_{}".format(box_name)))
    if os.path.exists(data_link):
        os.remove(data_link)
    os.symlink(parameters["experiment_path"], data_link)

    if preference_test:
        exp = PeckingAndPlaybackTest(**parameters)
    else:
        # Conditions can contain a "pecking" and a "playback" dict for preference tests
        # But if the preference flag is not set, then the only condition expected by
        # the PeckingTest experiment class is what is included under "pecking"
        if isinstance(parameters["conditions"], dict) and "pecking" in parameters["conditions"]:
            parameters["conditions"] = parameters["conditions"]["pecking"]
            parameters["queue_parameters"] = parameters["queue_parameters"]["pecking"]
        exp = PeckingTest(**parameters)

    exp.run()
