import logging

from slack_sdk import WebClient


class SlackFormatter(logging.Formatter):
    """Adds nice formatting for stack trace when posting to slack
    """

    def formatException(self, exc_info):
        result = super(SlackFormatter, self).formatException(exc_info)
        return "```\n{}\n```".format(result)


class SlackLogHandler(logging.Handler):
    """Log to slack channel

    Provides additional formatting codes %(annotation)s and %(emoji)s

    Implementation based on https://github.com/mathiasose/slacker_log_handler
    """
    EMOJIS = {
        logging.NOTSET: ':loudspeaker:',
        logging.DEBUG: ':speaker:',
        logging.INFO: ':information_source:',
        logging.WARNING: ':warning:',
        logging.ERROR: ':exclamation:',
        logging.CRITICAL: ':boom:'
    }

    def __init__(
            self,
            channel=None,
            username=None,
            annotation=None,
            token=None,
            timeout=1,
            format='%(annotation)s%(emoji)s *%(levelname)s* at %(asctime)s [%(name)s]\n%(message)s'
            ):
        logging.Handler.__init__(self)
        self.token = token
        self.channel = channel
        self.username = username
        self.annotation = annotation
        self.timeout = timeout

        self.client = WebClient(token=self.token, timeout=self.timeout)
        self.formatter = SlackFormatter(format)

    def _make_content(self, record):
        record.annotation = "{} ".format(self.annotation) if self.annotation else ""
        record.emoji = self.EMOJIS[record.levelno]
        # Another handler may modify record.exc_text directly, preventing SlackFormatter
        # from having a chance to. Clear it out so the formatting can be applied.
        record.exc_text = None
        content = {
            "text": self.format(record),
            "username": self.username,
            "channel": self.channel
        }
        return content

    def emit(self, record):
        try:
            content = self._make_content(record)
            self.client.chat_postMessage(**content)
        except:
            self.handleError(record)
