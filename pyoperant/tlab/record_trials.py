import os
import numpy as np


class RecordTrialsMixin(object):
    """Record audio during trials.
    """

    def get_wavfile_path(self):
        basename = os.path.basename(os.path.splitext(self.subject.filename)[0])
        folder = os.path.dirname(self.subject.filename)
        recording_filename = "trial{}.wav".format(self.this_trial.index)

        directory = os.path.join(
            folder,
            "audio_recordings",
            basename,
        )
        recording_path = os.path.join(
            directory,
            recording_filename
        )

        if not os.path.exists(directory):
            os.makedirs(directory)

        return recording_path

    def save_wavfile(self, data, rate, dest):
        if not os.path.exists(os.path.dirname(dest)):
            os.makedirs(os.path.dirname(dest))

        scipy.io.wavfile.write(dest, rate, data)

    def end(self):
        if self.panel.mic:
            self.panel.mic.input.interface.close()
        super(RecordTrialsMixin, self).end()
