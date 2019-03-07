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
from pyoperant.tlab import chronic_playback, record_trials
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


class ChronicWithOnlinePlayback(chronic_playback.ChronicPlayback, record_trials.RecordTrialsMixin):

    def __init__(self, intertrial_interval=2.0, *args, **kwargs):
        panel = kwargs.get("panel")
        kwargs["queue_parameters"]["state"] = panel.gui_state
        base.BaseExp.__init__(self, *args, **kwargs)
        self.intertrial_interval = intertrial_interval
        self.panel.gui.state["stimulus_dir"] = kwargs["conditions"]["online"].file_path

    def await_trigger(self):
        """Waiting period before trial begins

        Here, we handle any pending GUI events and wait for events if necessary
        """
        if isinstance(self.intertrial_interval, (list, tuple)):
            self.iti = np.random.uniform(*self.intertrial_interval)
        else:
            self.iti = self.intertrial_interval

        if self.panel.pause_button.status() == True:
            self.panel.gui.set_status(
                "Paused ({} mode)".format(self.panel.condition_button.status()))
            status = self.panel.quit_button.poll()
        else:
            status = self.panel.quit_button.poll(timeout=0)

        if status == MessageStatus.QUIT:
            raise KeyboardInterrupt
        elif status == MessageStatus.ABORT:
            raise trials.AbortTrial

        self.panel.gui.clear_events()

        condition_str = self.panel.condition_button.status()
        if condition_str == "normal":
            self.panel.gui.set_status({"iti": self.iti})
            status = self.panel.quit_button.poll(timeout=self.iti)
        elif condition_str == "online":
            status = self.panel.play_button.poll()

        if status == MessageStatus.QUIT:
            raise KeyboardInterrupt
        elif status == MessageStatus.ABORT:
            raise trials.AbortTrial

        self.panel.gui.set_status("Playing stimulus")

    def select_stimulus(self, condition):
        if isinstance(condition, stimuli.DynamicStimulusCondition):
            selected_stimulus = self.panel.stimulus_select.status()
            return condition.get(selected_stimulus)
        else:
            return super(ChronicWithOnlinePlayback, self).select_stimulus(condition)
