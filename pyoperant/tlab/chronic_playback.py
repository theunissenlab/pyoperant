import os
import re
import hashlib
import logging
import datetime as dt
import numpy as np
import scipy.io.wavfile
from pyoperant.behavior import simple_stimulus_playback
from pyoperant.errors import EndSession
from pyoperant.tlab import record_trials
from pyoperant import utils, stimuli

logger = logging.getLogger(__name__)


class ChronicPlayback(record_trials.RecordTrialsMixin, simple_stimulus_playback.SimpleStimulusPlayback):
    """ Theunissen lab simple playback experiment. For documentation of
    arguments see behavior.base.BaseExp and
    behavior.simple_stimulus_playback.SimpleStimulusPlayback
    """
    def __init__(self, recording_directory=None, *args, **kwargs):
        self.recording_directory = recording_directory
        super(ChronicPlayback, self).__init__(*args, **kwargs)

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
