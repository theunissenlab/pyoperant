from pyoperant.interfaces import console_


class KeyboardTrigger(console_.ConsoleInterface):

    def __init__(self, *args, **kwargs):
        trigger_on = kwargs.pop("trigger_on", None)
        super(KeyboardTrigger, self).__init__(*args,**kwargs)
        self.trigger_on = trigger_on

    def _read_bool(self, **params):
        if self.trigger_on is None:
            return self._read(prompt="Trigger (hit Enter) ")
        else:
            return self._read(prompt="Trigger (type '{}'): ".format(self.trigger_on))
