import os
import numpy as np


class RecordTrialsMixin(object):
    """Record audio during trials.
    """

    def get_wavfile_path(self):
        basename = os.path.basename(os.path.splitext(self.subject.filename)[0])
        recording_filename = "trial{}.wav".format(self.this_trial.index)

        directory = os.path.join(
            self.recording_directory,
            basename,
        )
        recording_path = os.path.join(
            directory,
            recording_filename
        )

        if not os.path.exists(directory):
            os.makedirs(directory)

        return recording_path

    def session_post(self):
        self.panel.mic.input.interface.close()
