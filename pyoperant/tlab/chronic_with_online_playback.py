#!/usr/bin/env python
import os
import sys
import logging
import csv
import datetime as dt
import random
import numpy as np
from pyoperant.behavior import base
from pyoperant.errors import EndSession
from pyoperant import states, trials, blocks
from pyoperant import components, utils, reinf, queues, configure, stimuli, subjects

logger = logging.getLogger(__name__)


class OnlineCondition(stimuli.DynamicStimulusConditionWav):
    """ Rewarded stimuli are rewarded if the subject does *not* respond (i.e.
    No-Go stimuli).
    """
    def __init__(self, file_path="", recursive=False):
        super(RewardedCondition, self).__init__(name="Online",
                                                response=False,
                                                is_rewarded=True,
                                                is_punished=False,
                                                file_path=file_path,
                                                recursive=recursive)


class OfflineCondition(stimuli.StimulusConditionWav):
    """ Unrewarded stimuli are not consequated and should be pecked through
    (i.e. Go stimuli)
    """
    pass


class State(object):
    def __init__(self):
        self._state = "offline"

    def set(self, new_state):
        self._state = new_state

    @property
    def state(self):
        return self._state


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

    def __init__(self, *args, **kwargs):
        self.experiment_state = State()
        kwargs["queue_parameters"]["state"] = self.experiment_state
        super(ChronicWithOnlinePlayback, self).__init__(*args, **kwargs)

        # Spin up a GUI here.
        self.experiment_state.set("offline")

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
        if isinstance(self.intertrial_interval, (list, tuple)):
            self.iti = np.random.uniform(*self.intertrial_interval)
        else:
            self.iti = self.intertrial_interval

        utils.wait(self.iti)

        if self.experiment_state.state == "online":
            self.panel.button.poll()

    def trial_pre(self):
        """ Store data that is specific to this experiment, and compute a wait time for an intertrial interval
        """
        stimulus = self.this_trial.stimulus.file_origin
        logger.debug("Waiting for %1.3f seconds" % self.iti)
        self.this_trial.annotate(stimulus_name=stimulus,
                                 intertrial_interval=self.iti)

    def stimulus_main(self):
        """ Queue the sound and play it, while adding metadata """

        logger.info("Trial %d - %s - %s" % (
                                     self.this_trial.index,
                                     self.this_trial.time.strftime("%H:%M:%S"),
                                     self.this_trial.stimulus.name
                                     ))

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
