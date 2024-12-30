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
        reward_event = self.panel.reward(value=self.reward_value) # First possible lag
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
            inactivity_before_playback=[5.0, 10.0], # between 5 and 10 minutes of inactivity
            inactivity_before_playback_restart=60.0 * 60, # if 1 hr goes by we can do playbacks again
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
        
        self.panel.speaker.set_gain(self.gain)
        if np.any(list(self.record_audio.values())):
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



class NoGoCondition(stimuli.StimulusConditionWav):
    """ NoGo stimuli are rewarded if the subject does *not* respond (i.e.
    No-Go stimuli).
    """
    def __init__(self, file_path="", recursive=False):
        super(NoGoCondition, self).__init__(name="No-Go",
                                                response=False,
                                                is_rewarded=True,
                                                is_punished=True,
                                                file_path=file_path,
                                                recursive=recursive)


class GoCondition(stimuli.StimulusConditionWav):
    """ Go stimuli are rewarded when the subject pecks
    (i.e. Go stimuli)
    """
    def __init__(self, file_path="", recursive=False):
        super(GoCondition, self).__init__(name="Go",
                                                  response=True,
                                                  is_rewarded=True,
                                                  is_punished=True,
                                                  file_path=file_path,
                                                  recursive=recursive)


class PeckingDelayTest(PeckingTest):
    """A go no-go task with a forced choice after a set delay
            |Stimulus|Delay|Response|Reward/Punish|
    Parameters
    ----------
    block_queue: dict

    Additional Parameters
    ---------------------
    TODO

    For all other parameters, see pyoperant.behavior.base.BaseExp and
    pyoperant.behavior.GoNoGoInterrupt and pyoperant.tlab.PeckingTest
    """
    def __init__(self, *args, **kwargs):
        super(PeckingTest, self).__init__(*args, **kwargs)
        self.stim_time = self.parameters.get("stim_time", None)
        self.delay_time = self.parameters.get("delay_time", .5)
        self.response_time = self.parameters.get("response_time", 2)
        self.punish_file = self.parameters.get("punish_file",None)
        self.punish_time = self.parameters.get("punish_time",2)
        self.post_punish_delay = self.parameters.get("post_punish_delay",2)

    def stimulus_main(self):
        """ Queue the stimulus and play it back """
        logger.info("Trial %d - %s - %s - %s - %s" % (
                                     self.this_trial.index,
                                     self.this_trial.time.strftime("%H:%M:%S"),
                                     self.this_trial.condition.name,
                                     self.this_trial.stimulus.name,
                                     self.stim_time))
        self.panel.speaker.queue(self.this_trial.stimulus.file_origin,
                                 cutoff_time=self.stim_time)
        self.this_trial.annotate(stimulus_time=dt.datetime.now())
        self.panel.speaker.play()

    def response_pre(self):
        """Wait the delay period before waiting for a response"""
        # hard code wait time to 2 s
        self.panel.response_port.off()
        # listen for pecks to record if they are pecking in the delay
        end_time = dt.datetime.now() + dt.timedelta(seconds=self.delay_time)
        self.this_trial.n_early_pecks = -1
        # this loop essentially waits until end time but counts the number of
        # pecks received in that time for logging purposes
        while dt.datetime.now() < end_time:
            secs = (end_time-dt.datetime.now()).total_seconds()
            logger.info("Polling for %s seconds Before Response phase" %secs)
            self.panel.response_port.poll(secs)
            self.this_trial.n_early_pecks += 1

        self.this_trial.annotate(delay_period_pecks=self.this_trial.n_early_pecks)
        logger.debug("Received %s early pecks during the delay period"%self.this_trial.n_early_pecks)

        # put on the button light to indicate that the response phase as begun
        self.panel.response_port.on()

    def response_main(self):
        """ Poll for an interruption for the duration of the response time. """
        start_of_response = dt.datetime.now()
        end_time = dt.datetime.now() + dt.timedelta(seconds=self.response_time)

        # this loop essentially waits until end time but counts the number of
        # pecks received in that time for logging purposes
        logger.info("Polling for response for %s seconds" %self.response_time)
        self.this_trial.response_time = self.panel.response_port.poll(self.response_time)
        # while dt.datetime.now() < end_time:
        #     secs = (end_time-dt.datetime.now()).total_seconds()
        #     logger.info("Polling for response for %s seconds" %secs)
        #     self.panel.response_port.poll(secs)
        #     break

        logger.debug("Received peck or timeout, providing reward or punishment.")

        # Its janky, but allow the stimulus to finish...
        # it does suppress pecks in this cleanup period.
        # Thats why it would be better to link the polling period
        # with the playback completion itself
        if not self.this_trial.response_time:
            self.panel.speaker.stop()
            # _start = time.time()
            # self.panel.speaker.let_finish()
            # logger.debug("go_no_go_interrupt.py: Waited {:.6f}s extra for stim to finish".format(time.time() - _start))
        else:
            self.panel.speaker.stop()

        logger.debug("Playback stopped")

        if self.this_trial.response_time is None:
            logger.info("No peck was received")
            self.this_trial.response = False
            self.start_immediately = False  # Next trial will poll for a response before beginning
            self.this_trial.rt = np.nan
        else:
            logger.info("Peck was received")
            self.this_trial.response = True
            self.start_immediately = False  # Next trial will begin immediately
            self.this_trial.rt = self.this_trial.response_time - start_of_response

    def reward_main(self):
        """ Reward a correct response"""
        logger.info("Supplying reward for %3.2f seconds" % self.reward_value)
        reward_event = self.panel.reward(value=self.reward_value, and_poll=False)

    def punish_main(self):
        """Punish incorrect response"""
        self.panel.response_port.off()
        self.panel.house_light.off()
        # logger.info("playing tone for punishment, no food")
        # if self.punish_file is not None:
        #     self.panel.speaker.queue(self.punish_file, self.punish_time)
        #     self.panel.speaker.play()
        # self.panel.speaker.let_finish()
        utils.wait(self.post_punish_delay)
        self.panel.house_light.on()
        self.panel.response_port.on()


class PeckingDMTS(PeckingTest):
    """A delay match to category task

    Stim A  --> delay --> Stim A --> peck --> Reward
                    \           \--> wait --> Punish
                     \--> Stim B --> peck --> Punish
                                \--> wait --> Stim A --> peck --> Reward
                                                    \--> wait --> Punish
    Parameters
    ----------
    block_queue: dict

    Additional Parameters
    ---------------------
    TODO

    For all other parameters, see pyoperant.behavior.base.BaseExp and
    pyoperant.behavior.GoNoGoInterrupt and pyoperant.tlab.PeckingTest
    """
    def __init__(self, *args, **kwargs):
        super(PeckingTest, self).__init__(*args, **kwargs)
        self.stim_time = self.parameters.get("stim_time", None)
        self.delay_time = self.parameters.get("delay_time", .5)
        self.response_time = self.parameters.get("response_time", 2)
        self.punish_file = self.parameters.get("punish_file",None)
        self.punish_time = self.parameters.get("punish_time",2)
        self.post_punish_delay = self.parameters.get("post_punish_delay",2)

    def trial_pre(self):
        """ Initialize the trial and, if necessary, wait for a peck before
        starting stimulus playback.
        """
        logger.debug("Starting trial #%d" % self.this_trial.index)
        stimulus = self.this_trial.stimulus
        condition = self.this_trial.condition.name
        self.this_trial.annotate(stimulus_name=",".join([s.file_origin for s in stimulus]),
                                 condition_name=condition)


    def stimulus_main(self):
        """ Queue the stimulus and play it back """
        logger.info("Trial %d - %s - %s - %s - %s" % (
                                     self.this_trial.index,
                                     self.this_trial.time.strftime("%H:%M:%S"),
                                     self.this_trial.condition.name,
                                     "".join([s.name for s in self.this_trial.stimulus]),
                                     self.stim_time))
        # Turn off response port prior to playing audio and wait .5 sec
        self.panel.response_port.off()
        utils.wait(secs=.5)
        self.panel.speaker.queue(self.this_trial.stimulus[0].file_origin,
                                 cutoff_time=self.stim_time)
        self.this_trial.annotate(stimulus_time=dt.datetime.now())
        start = dt.datetime.now()
        self.panel.speaker.play()
        #stim_end = dt.datetime.now() + dt.timedelta(seconds=self.stim_time)
        self.panel.speaker.let_finish()
        logger.debug("Stim took %s time"%(dt.datetime.now() - start))

        """Wait the delay period before waiting for a response"""
        utils.wait(secs = self.delay_time)

        # stim_end = dt.datetime.now() + dt.timedelta(seconds=self.stim_time)
        #
        # while dt.datetime.now() < stim_end:
        #     secs = (stim_end-dt.datetime.now()).total_seconds()
        #     logger.info("Polling for %s seconds" %secs)
        #     self.panel.response_port.poll(secs)
        #     self.this_trial.n_early_pecks += 1


    def response_pre(self):
        return

    def response_main(self):
        """ Poll for response, then play match if it was a no-match trial """
        """Play the second stimulus"""
        self.this_trial.response_time  = None
        for stim in self.this_trial.stimulus[1:]:
            # if you peck to a stim that isnt the last stim you lose
            if self.this_trial.response_time is not None:
                self.this_trial.response_time = None
                break
            self.panel.speaker.queue(stim.file_origin,
                                 cutoff_time=self.stim_time)

            start = dt.datetime.now()
            self.panel.speaker.play()
            #stim_end = dt.datetime.now() + dt.timedelta(seconds=self.stim_time)
            self.panel.speaker.let_finish()
            stim_end = dt.datetime.now()
            logger.debug("Stim took %s time"%(stim_end - start))

            # Poll for response
            # put on the button light to indicate that the response phase as begun
            self.panel.response_port.on()
            start_of_response = dt.datetime.now()
            end_time = dt.datetime.now() + dt.timedelta(seconds=self.response_time)

            # this loop essentially waits until end time but counts the number of
            # pecks received in that time for logging purposes
            self.this_trial.response_time = None
            self.this_trial.response_time = self.panel.response_port.poll(self.response_time)
            while dt.datetime.now() < end_time:
                secs = (end_time-dt.datetime.now()).total_seconds()
                logger.info("Polling for response for %s seconds" %secs)
                self.panel.response_port.poll(secs)
            self.panel.speaker.stop()
            self.panel.response_port.off()
            utils.wait(secs=.5)
            logger.debug("Received peck or timeout, providing reward or punishment.")


        if self.this_trial.response_time is None:
            logger.info("No peck was received in the appropriate time")
            self.this_trial.response = False
            self.start_immediately = False  # Next trial will poll for a response before beginning
            self.this_trial.rt = np.nan
        else:
            logger.info("Peck was received")
            self.this_trial.response = True
            self.start_immediately = False  # Next trial will begin immediately
            self.this_trial.rt = self.this_trial.response_time - start_of_response

    def reward_main(self):
        """ Reward a correct response"""
        logger.info("Supplying reward for %3.2f seconds" % self.reward_value)
        reward_event = self.panel.reward(value=self.reward_value, and_poll=False)

    def punish_main(self):
        """Punish incorrect response"""
        # punish with a timeout
        self.panel.response_port.off()
        self.panel.house_light.off()
        utils.wait(self.post_punish_delay)
        self.panel.response_port.on()
        self.panel.house_light.on()
        #logger.info("playing tone for punishment, no food")
        #if self.punish_file is not None:
        #    self.panel.speaker.queue(self.punish_file, self.punish_time)
        #    self.panel.speaker.play()
        #self.panel.speaker.let_finish()
        #utils.wait(self.post_punish_delay)
        #self.panel.response_port.on()
from build.lib.pyoperant.utils import get_object_from_string

if __name__ == '__main__':
    # Pecking Test  
    from pyoperant import configure
    import shutil
    from pyoperant.tlab.chronic_playback import ChronicPlayback
    import gc

    playback_cfg = "I:\OperantEphys\HpiRed7670F\Configs\HpiRed7670F_playback_d1.yaml"
    operant_cfg = "I:\OperantEphys\HpiRed7670F\Configs\HpiRed7670F_operant_d1.yaml" 

    experiment_sequence = ['operant', 'playback']
    cur_state = 0
    while True:
        cur_exp = experiment_sequence[cur_state]
        if cur_exp == 'operant':
            print("running operant")
            operant_c = configure.ConfigureYAML.load(operant_cfg)
            conditions = operant_c['conditions'].copy()
            operant_c['timeout_secs'] = 20 * 60 # 20 mins idle time before playback experiment starts
            conditions_list = []     
            for condition_dict in conditions:
                condition = get_object_from_string(condition_dict['class'])
                conditions_list.append(condition(file_path=condition_dict["file_path"]))
            operant_c['conditions'] = conditions_list
            exp = PeckingTest(**operant_c)
            # copy the yaml file used for this experiment to the experiment path
            out_path = os.path.join(exp.experiment_path,"%s_%s_config.yaml"%(exp.subject.name,exp.timestamp))
            shutil.copy(operant_cfg,out_path)
            #run the experiment
            exp.run()
            del exp, operant_c
        elif cur_exp == 'playback':
            print("running playback")
            playback_c = configure.ConfigureYAML.load(playback_cfg)
            exp = ChronicPlayback(**playback_c)
            out_path = os.path.join(exp.experiment_path,"%s_%s_config.yaml"%(exp.subject.name,exp.timestamp))
            shutil.copy(playback_cfg,out_path)
            exp.run()
            del exp, playback_c
        else:
            raise ValueError("Unknown experiment %s"%cur_exp)
        gc.collect()
        cur_state = abs(cur_state - 1) # Toggle from 0 to 1 or 1 to 0