#!/usr/bin/env python
import hashlib
import os
import sys
import logging
import csv
import datetime as dt
import numpy as np
import random
import time
from pyoperant.behavior import base
from pyoperant.errors import EndSession
from pyoperant import states, trials, blocks
from pyoperant import components, utils, reinf, queues, configure, stimuli, subjects

from pyoperant.interfaces.utils import MessageStatus

logger = logging.getLogger(__name__)


class OnlineCondition(stimuli.DynamicStimulusConditionWav):
    """ Rewarded stimuli are rewarded if the subject does *not* respond (i.e.
    No-Go stimuli).
    """
    def __init__(self, file_path="", recursive=False):
        super(OnlineCondition, self).__init__(name="Online",
                                                response=False,
                                                is_rewarded=True,
                                                is_punished=False,
                                                file_path=file_path,
                                                recursive=recursive)


class NormalCondition(stimuli.StimulusConditionWav):
    """ Unrewarded stimuli are not consequated and should be pecked through
    (i.e. Go stimuli)
    """
    pass


class ChronicWithOnlinePlayback(base.BaseExp):

    req_panel_attr = ["sleep",
                      "reset",
                      "idle",
                      "ready",
                      "speaker"]

    fields_to_save = ['session',
                      'index',
                      'time',
                      'stimulus_name',
                      'intertrial_interval']

    def __init__(self, intertrial_interval=2.0, *args, **kwargs):
        panel = kwargs.get("panel")
        kwargs["queue_parameters"]["state"] = panel.gui_state
        super(ChronicWithOnlinePlayback, self).__init__(*args, **kwargs)
        self.intertrial_interval = intertrial_interval
        self.panel.gui.state["stimulus_dir"] = kwargs["conditions"]["online"].file_path

    def session_main(self):
        """ Runs the session by looping over the block queue and then running
        each trial in each block.
        """
        # TODO: can update state here for gui updates?

        for self.this_block in self.block_queue:
            self.this_block.experiment = self
            logger.info("Beginning block #%d" % self.this_block.index)
            for trial in self.this_block:
                trial.run()

    def await_trigger(self):
        """Handle GUI events and wait for appropriate trigger to start trial
        """
        if isinstance(self.intertrial_interval, (list, tuple)):
            self.iti = np.random.uniform(*self.intertrial_interval)
        else:
            self.iti = self.intertrial_interval

        if self.panel.pause_button.status() == True:
            status = self.panel.quit_button.poll()
        else:
            status = self.panel.quit_button.poll(timeout=0)

        if status == MessageStatus.QUIT:
            raise KeyboardInterrupt
        elif status == MessageStatus.ABORT:
            raise trials.AbortTrial

        self.panel.gui.clear_events()

        condition = self.panel.condition_button.status()
        if condition == "normal":
            self.panel.gui.set_status({"iti": self.iti})
            status = self.panel.quit_button.poll(timeout=self.iti)
        elif condition == "online":
            status = self.panel.play_button.poll()

        if status == MessageStatus.QUIT:
            raise KeyboardInterrupt
        elif status == MessageStatus.ABORT:
            raise trials.AbortTrial

    def trial_pre(self):
        """ Store data that is specific to this experiment, and compute a wait time for an intertrial interval
        """
        stimulus = self.this_trial.stimulus.file_origin
        logger.debug("Waiting for %1.3f seconds" % self.iti)
        self.this_trial.annotate(stimulus_name=stimulus,
                                 intertrial_interval=self.iti)

    def stimulus_main(self):
        """ Queue the sound and play it, while adding metadata """
        self.panel.gui.set_status("Playing stimulus {}.".format(
            os.path.basename(self.this_trial.stimulus.file_origin)
        ))

        logger.info("Trial %d - %s - %s" % (
                                     self.this_trial.index,
                                     self.this_trial.time.strftime("%H:%M:%S"),
                                     self.this_trial.stimulus.name
                                     ))

        # TODO: put in  meta data whether this was an automatic or manual trial

        # Set up metadata
        repetition = int(self.this_trial.index / len(self.this_trial.condition.files))
        repetition = "%04d" % repetition

        # Get the digits in the filename or choose the first 4.
        # filename = os.path.basename(self.this_trial.stimulus.file_origin)
        # m = re.findall("\d+", filename)
        # if len(m) > 0:
        #     name = "%04d" % int(m[0])
        # else:
        #     logger.warning("Stimulus file should be numbered! %s" % filename)
        #     filename = os.path.splitext(filename)[0]
        #     name = filename.ljust(4)[-4:]

        # Get the trial index as a string
        trial_index = "%04d" % self.this_trial.index

        # Get the md5 hash
        md5 = hashlib.md5()
        with open(self.this_trial.stimulus.file_origin, "r") as fh:
            md5.update(fh.read())
        md5 = str(md5.hexdigest())

        metadata = "".join([repetition, trial_index, md5])

        self.panel.speaker.queue(self.this_trial.stimulus.file_origin,
                                 metadata=metadata)
        self.panel.speaker.play()

        # Wait for stimulus to finish
        utils.wait(self.this_trial.stimulus.duration)
