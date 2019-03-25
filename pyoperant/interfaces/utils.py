from contextlib import contextmanager
from enum import Enum

@contextmanager
def buffered_analog_output(data, chunk_size, buffer_size):

    pass


class MessageStatus(Enum):
    QUIT = 0
    NORMAL = 1
    ABORT = 2

