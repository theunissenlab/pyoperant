import queue


class RecordTrialsMixin(object):

    def stimulus_pre(self):
        super(RecordTrialsMixin, self).stimulus_pre()
        self.panel.mic.record()

    def response_post(self):
        super(RecordTrialsMixin, self).response_post()
        self.panel.mic.stop()
        # consume data and save it
        data = []
        while True:
            try:
                data.append(self.panel.mic.queue.get())
            except queue.Empty:
                break
        data = np.concatenate(data)
        self.save_recording(data)

    def save_recording(data):
        """Save recorded data to wavfile"""
        print(data.shape)
        pass
