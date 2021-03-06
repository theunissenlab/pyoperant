#!/usr/bin/env python
import os
import logging
import datetime as dt
import time

import numpy as np

import pyoperant.blocks as blocks_
from pyoperant import configure
from pyoperant import stimuli
from pyoperant.tlab.custom_logging import PollingFilter, AudioPlaybackFilter
from pyoperant.behavior.go_no_go_interrupt import GoNoGoInterrupt
from pyoperant.tlab import local_tlab, record_trials
from pyoperant import queues
from pyoperant import utils

logger = logging.getLogger(__name__)


class ProbeCondition(stimuli.StimulusConditionWav):
    """ Probe stimuli are not consequated and should be sampled as evenly as
    possible. This is done by setting replacement to False and shuffle to True.
    """

    def __init__(self, name="Probe",
                 response=False,
                 is_rewarded=False,
                 is_punished=False,
                 replacement=False,
                 shuffle=True,
                 *args, **kwargs):

        super(ProbeCondition, self).__init__(name=name,
                                             response=response,
                                             is_rewarded=is_rewarded,
                                             is_punished=is_punished,
                                             replacement=replacement,
                                             shuffle=shuffle,
                                             *args, **kwargs)


class PlaybackCondition(stimuli.StimulusConditionWav):
    """ Probe stimuli are not consequated and should be sampled as evenly as
    possible. This is done by setting replacement to False and shuffle to True.
    """

    def __init__(self, name="Playback",
                 response=False,
                 is_rewarded=False,
                 is_punished=False,
                 *args, **kwargs):

        super(PlaybackCondition, self).__init__(name=name,
                                             response=response,
                                             is_rewarded=is_rewarded,
                                             is_punished=is_punished,
                                             *args, **kwargs)


class PeckingTest(GoNoGoInterrupt):
    """A go no-go interruption experiment for the Theunissen lab

    Additional Parameters
    ---------------------
    log_polling: bool
        Whether to log polling of the pecking key (value every ~100 ms)
    log_polling_file: string
        Filename for the polling log
    log_playback: bool
        Whether to log explicitly stimulus playback times (probably obsolete)
    log_playback_file: string
        Filename for playback log

    For all other parameters, see pyoperant.behavior.base.BaseExp and
    pyoperant.behavior.GoNoGoInterrupt
    """
    def __init__(self, *args, **kwargs):
        super(PeckingTest, self).__init__(*args, **kwargs)

        # if self.parameters.get("log_polling", False):
        #     self.config_polling_log()
        if self.parameters.get("log_playback", False):
            self.config_playback_log()

    def config_polling_log(self):
        filename = self.parameters.get("log_polling_file", "keydata.log")
        if len(os.path.split(filename)[0]) == 0:
            filename = os.path.join(self.experiment_path, filename)

        polling_handler = logging.FileHandler(filename)
        polling_handler.setLevel(logging.DEBUG)
        polling_handler.setFormatter(logging.Formatter("%(asctime)s: %(message)s"))
        polling_filter = PollingFilter()
        polling_handler.addFilter(polling_filter)

        logger = logging.getLogger("pyoperant.interfaces.arduino_")
        logger.setLevel(logging.DEBUG)
        logger.addHandler(polling_handler)

        logger = logging.getLogger()
        for handler in logger.handlers:
            if handler.level < logger.level:
                handler.setLevel(logger.level)

    def config_playback_log(self):

        filename = self.parameters.get("log_playback_file",
                                       "audio_playback.log")
        if len(os.path.split(filename)[0]) == 0:
            filename = os.path.join(self.experiment_path, filename)

        playback_handler = logging.FileHandler(filename)
        playback_handler.setLevel(logging.DEBUG)
        playback_handler.setFormatter(logging.Formatter("%(asctime)s: %(message)s"))
        playback_filter = AudioPlaybackFilter()
        playback_handler.addFilter(playback_filter)

        logger = logging.getLogger("pyoperant.interfaces.pyaudio_")
        logger.setLevel(logging.DEBUG)
        logger.addHandler(playback_handler)

        logger = logging.getLogger()
        for handler in logger.handlers:
            if handler.level < logger.level:
                handler.setLevel(logger.level)

    def save(self):
        """
        Save the experiment parameters
        """

        self.snapshot_f = os.path.join(self.experiment_path,
                                       "configuration.yaml")
        logger.debug("Saving configurations as %s" % self.snapshot_f)
        configure.ConfigureYAML.save(self.parameters,
                                     self.snapshot_f,
                                     overwrite=True)

    def reward_main(self):
        """
        Custom reward method to put the feeder up during the reward period but still respond to pecks. If the key is pecked, the next trial begins immediately.
        :return:
        """
        logger.info("Supplying reward for %3.2f seconds" % self.reward_value)
        reward_event = self.panel.reward(value=self.reward_value)
        # There was a response during the reward period
        if isinstance(reward_event, dt.datetime):
            self.this_trial.reward = False  # maybe use reward_event here instead?
            self.start_immediately = True


class PeckingAndPlaybackTest(PeckingTest, record_trials.RecordTrialsMixin):
    """A go no-go interruption experiment combined with occasional playbacks

    Parameters
    ----------
    block_queue: dict

    Additional Parameters
    ---------------------
    TODO

    For all other parameters, see pyoperant.behavior.base.BaseExp and
    pyoperant.behavior.GoNoGoInterrupt and pyoperant.tlab.PeckingTest
    """

    def __init__(
            self,
            block_queue=queues.block_queue,
            conditions=None,
            inactivity_before_playback=[5.0, 20.0],
            inactivity_before_playback_restart=3600.0,
            queue=queues.random_queue,
            queue_parameters=None,
            record_audio=None,
            recorded_audio_path=None,
            reinforcement=None,
            *args,
            **kwargs
        ):

        pecking_block = blocks_.Block(
            conditions["pecking"],
            queue=queue,
            reinforcement=reinforcement,
            **queue_parameters["pecking"]
        )

        playback_block = blocks_.Block(
            conditions["playback"],
            queue=queue,
            **queue_parameters["playback"]
        )

        block_queue = blocks_.MixedBlockHandler(
            pecking=pecking_block,
            playback=playback_block,
        )

        self.record_audio = record_audio
        self.recording_key = None
        self.recording_directory = recorded_audio_path

        self.inactivity_before_playback = inactivity_before_playback
        self.inactivity_before_playback_restart = inactivity_before_playback_restart

        # Will not start playbacks unless subject has started pecking
        self._delay_before_first_playback = inactivity_before_playback_restart
        self.last_playback_reset = dt.datetime.now()

        super().__init__(*args, block_queue=block_queue, **kwargs)

        if np.any([self.record_audio.values()]):
            if not hasattr(self.panel, "mic"):
                logger.error("Cannot record audio if panel has no mic.")
                self.end()

    def get_seconds_from_last_reset(self):
        return (dt.datetime.now() - self.last_playback_reset).total_seconds()

    def trial_iter(self, block_queue):
        for block in block_queue.blocks.values():
            block.experiment = self

        while not block_queue.check_completion():
            if not self.start_immediately:
                if block_queue.check_completion("playback"):
                    since_reset = self.get_seconds_from_last_reset()
                    timeout = self.inactivity_before_playback_restart - since_reset
                else:
                    # The first timeout should be extra long to let the experimenter get set up
                    # and the subject can calm down. Once the bird has started pecking, playbacks
                    # will occur at normal intervals.
                    timeout = self._delay_before_first_playback + np.random.uniform(*self.inactivity_before_playback)
                    self._delay_before_first_playback = 0
                response = self.panel.response_port.poll(timeout=timeout)
            else:
                response = True

            if response is None:  # timeout
                if block_queue.check_completion("playback"):
                    self.last_playback_reset = dt.datetime.now()
                    block_queue.reset_one("playback")
                yield block_queue.next_trial("playback")
            else:
                yield block_queue.next_trial("pecking")

    def stimulus_pre(self):
        super(PeckingAndPlaybackTest, self).stimulus_pre()
        self._stim_start_time = time.time()
        for block_name in self.block_queue.blocks:
            if self.this_trial.block == self.block_queue.blocks[block_name]:
                self.panel.speaker.set_gain(self.gain.get(block_name, None))
                break

    def response_main(self):
        if self.this_trial.block == self.block_queue.blocks["pecking"]:
            GoNoGoInterrupt.response_main(self)
        else:
            self.this_trial.rt = np.nan
            utils.wait(self.this_trial.stimulus.duration)
            self.panel.speaker.stop()

    def response_post(self):
        super(PeckingAndPlaybackTest, self).response_post()

        # If this is a block we are supposed to record, save the last whatever seconds
        for block_name in self.record_audio:
            if self.record_audio[block_name] and self.this_trial.block == self.block_queue.blocks[block_name]:
                utils.wait(2.0)  # Record for two extra second after the end of the stim and 6 seconds before stim onset
                data, rate = self.panel.mic.record_last(6.0 + (time.time() - self._stim_start_time))
                self.save_wavfile(data, rate, self.get_wavfile_path())
                break
