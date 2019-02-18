import logging
import numpy as np
from pyoperant.tlab.chronic_playback import ChronicPlayback
from pyoperant import stimuli, utils


logger = logging.getLogger(__name__)


class ChronicTriggeredPlayback(ChronicPlayback):
        """ Theunissen lab simple button-triggered playback experiment.
        For documentation of arguments see behavior.base.BaseExp and
        behavior.simple_stimulus_playback.SimpleStimulusPlayback
        """

        req_panel_attr = [
            "sleep",
            "reset",
            "idle",
            "ready",
            "speaker",
            "button",
        ]

        def await_trigger(self):
            # Reuse existing intertrial interval code...
            super(ChronicTriggeredPlayback, self).await_trigger()

            # ...then wait for the trial to be triggered externally
            self.panel.button.poll()


class ChronicTriggeredPlaybackDynamic(ChronicTriggeredPlayback):
        """ Theunissen lab simple button-triggered playback experiment.
        For documentation of arguments see behavior.base.BaseExp and
        behavior.simple_stimulus_playback.SimpleStimulusPlayback
        """

        StimulusCondition = stimuli.DynamicStimulusConditionWav
