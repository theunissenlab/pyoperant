import os
import queue
import numpy as np


class RecordTrialsMixin(object):

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

    def stimulus_pre(self):
        super(RecordTrialsMixin, self).stimulus_pre()
        self.key = self.panel.mic.record(
            duration=2,
            dest=self.get_wavfile_path()
        )

    def response_post(self):
        super(RecordTrialsMixin, self).response_post()
        self.panel.mic.stop(self.key)
    
    def session_post(self):
        self.panel.mic.input.interface.close()
