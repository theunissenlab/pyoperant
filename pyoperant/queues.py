import random
from pyoperant.utils import rand_from_log_shape_dist
import pickle
import numpy as np
import logging

logger = logging.getLogger(__name__)


def random_queue(items, weights=None, max_items=None):
    """ Generator which randomly samples items, with replacement

    Parameters
    ----------
    items: list
        A list of items to be queued
    weights: list
        A list of weights, 1 for each item in items
    max_items: int
        Maximum number of items to generate. (default: None)

    Yields
    ------
    A single item at each iteration
    """
    if len(items) == 0:
        raise ValueError("Cannot intialize a queue with 0 items")

    if weights is None:
        weights = [1.0 / len(items)] * len(items)
    else:
        weights = [float(ww) / sum(weights) for ww in weights]

    ii = 0
    while True:
        if (max_items is not None) and (ii >= max_items):
            break
        yield np.random.choice(items, p=weights)
        ii += 1


def block_queue(items, repetitions=1, shuffle=False):
    """ Generator which samples items in blocks

    Parameters
    ----------
    items: list
        A list of items to be queued
    repetitions: int
        The number of times each item in items will be presented (default: 1)
    shuffle: bool
        Shuffles the queue (default: False)

    Yields
    ------
    A single item at each iteration
    """
    items_repeated = []
    for rr in range(repetitions):
        items_repeated += items
    items = items_repeated

    if shuffle:
        random.shuffle(items)

    for item in items:
        yield item

class AdaptiveBase(object):
    """docstring for AdaptiveBase
    This is an abstract object for implementing adaptive procedures, such as
    a staircase. Importantly, any objects inheriting this need to define the
    `update()` and `next()` methods.
    """
    def __init__(self, **kwargs):
        self.updated = True # for first trial, no update needed
        self.update_error_str = "queue hasn't been updated since last trial"

    def __iter__(self):
        return self

    def update(self, correct, no_resp):
        self.updated = True
        if no_resp:
            self.no_response()

    def next(self):
        if not self.updated: #hasn't been updated since last trial
            raise Exception(self.update_error_str)
        self.updated = False

    def no_response(self):
        pass

    def on_load(self):
        try:
            super(AdaptiveBase, self).on_load()
        except AttributeError:
            pass
        self.updated = True
        self.no_response()

class PersistentBase(object):
    """
    A mixin that allows for the creation of an obj through a load command that
    first checks for a pickled file to load an object before generating a new one.
    """
    def __init__(self, filename=None, **kwargs):
        assert filename != None
        super(PersistentBase, self).__init__(**kwargs)
        self.filename = filename
        self.save()

    @classmethod
    def load(cls, filename, *args, **kwargs):
        try:
            with open(filename, 'rb') as handle:
                ab = pickle.load(handle)
                ab.on_load()
            return ab
        except IOError:
            return cls(*args, filename=filename, **kwargs)

    def on_load(self):
        try:
            super(PersistentBase, self).on_load()
        except AttributeError:
            pass

    def save(self):
        with open(self.filename, 'wb') as handle:
            pickle.dump(self, handle)


class KaernbachStaircase(AdaptiveBase):
    """ generates values for a staircase procedure from Kaernbach 1991
    This procedure returns values for each trial and assumes that larger values are
    easier. Thus, after a correct trial, the next value returned will be smaller and
    after incorrect trials, the next value returned will be larger. The magnitudes of
    these changes are stepsize_dn and stepsize_up, respectively.
    Args:
        start_val (float/int): the starting value of the procedure (default: 100)
    Kwargs:
        stepsize_up (int): number of steps to take after incorrect trial (default: 3)
        stepsize_dn (int): number of steps to take after correct trial (default: 1)
        min_val (float): minimum parameter value to allow (default: 0)
        max_val (float): maximum parameter value to allow (default: 100)
        crit (int): minimum number of trials (default: 0)
        crit_method (int): maximum number of trials (default: 100)
    Returns:
        float
    """
    def __init__(self,
                 start_val=100,
                 stepsize_up=3,
                 stepsize_dn=1,
                 min_val=0,
                 max_val=100,
                 crit=100,
                 crit_method='trials'
                 ):
        super(KaernbachStaircase, self).__init__()
        self.val = start_val
        self.stepsize_up = stepsize_up
        self.stepsize_dn = stepsize_dn
        self.min_val = min_val
        self.max_val = max_val
        self.crit = crit
        self.crit_method = crit_method
        self.counter = 0
        self.going_up = False

    def update(self, correct, no_resp):
        super(KaernbachStaircase, self).update(correct, no_resp)

        self.val += -1*self.stepsize_dn if correct else self.stepsize_up

        if self.crit_method=='reversals':
            if correct==self.going_up: # checks if last trial's perf was consistent w/ trend
                self.counter += 1
                self.going_up = not self.going_up

        # stop at max/min if we hit the rails
        if (self.max_val!=None) and (self.val > self.max_val):
            self.val = self.max_val
        elif (self.min_val!=None) and (self.val < self.min_val):
            self.val = self.min_val

    def next(self):
        super(KaernbachStaircase, self).next()
        if self.counter > self.crit:
            raise StopIteration
        self.counter += 1 if self.crit_method=='trials' else 0
        return self.val

class DoubleStaircase(AdaptiveBase):
    """
    Generates conditions from a list of stims that monotonically vary from most
    easily left to most easily right
    i.e. left is low and right is high

    The goal of this queue is to estimate the 50% point of a psychometric curve.

    This will probe left and right trials, if the response is correct, it will
    move the indices closer to each other until they are adjacent.

    stims: an array of stimuli names ordered from most easily left to most easily right
    rate_constant: the step size is the rate_constant*(high_idx-low_idx)
    """
    def __init__(self, stims, rate_constant=.05, **kwargs):
        super(DoubleStaircase, self).__init__(**kwargs)
        self.stims = stims
        self.rate_constant = rate_constant
        self.low_idx = 0
        self.high_idx = len(self.stims) - 1
        self.trial = {}
        self.update_error_str = "double staircase queue %s hasn't been updated since last trial" % (self.stims[0])

    def update(self, correct, no_resp):
        super(DoubleStaircase, self).update(correct, no_resp)
        if correct:
            if self.trial['low']:
                self.low_idx = self.trial['value']
            else:
                self.high_idx = self.trial['value']
        self.trial = {}

    def next(self):
        super(DoubleStaircase, self).next()
        if self.high_idx - self.low_idx <= 1:
            raise StopIteration

        delta = int(np.ceil((self.high_idx - self.low_idx) * self.rate_constant))
        if random.random() < .5: # probe low side
            self.trial['low'] = True
            self.trial['value'] = self.low_idx + delta
            return {'class': 'L',  'stim_name': self.stims[self.trial['value']]}
        else:
            self.trial['low'] = False
            self.trial['value'] = self.high_idx - delta
            return {'class': 'R',  'stim_name': self.stims[self.trial['value']]}

    def no_response(self):
        super(DoubleStaircase, self).no_response()
        self.trial = {}

class DoubleStaircaseReinforced(AdaptiveBase):
    """
    Generates conditions as with DoubleStaircase, but 1-probe_rate proportion of
    the trials easier/known trials to reduce frustration.

    Easier trials are sampled from a log shaped distribution so that more trials
    are sampled from the edges than near the indices

    stims: an array of stimuli names ordered from most easily left to most easily right
    rate_constant: the step size is the rate_constant*(high_idx-low_idx)
    probe_rate: proportion of trials that are between [0, low_idx] or [high_idx, length(stims)]
    """
    def __init__(self, stims, rate_constant=.05, probe_rate=.1, sample_log=False, **kwargs):
        super(DoubleStaircaseReinforced, self).__init__(**kwargs)
        self.dblstaircase = DoubleStaircase(stims, rate_constant)
        self.stims = stims
        self.probe_rate = probe_rate
        self.sample_log = sample_log
        self.last_probe = False
        self.update_error_str = "reinforced double staircase queue %s hasn't been updated since last trial" % (self.stims[0])

    def update(self, correct, no_resp):
        super(DoubleStaircaseReinforced, self).update(correct, no_resp)
        if self.last_probe:
            self.dblstaircase.update(correct, no_resp)
        self.last_probe = False

    def next(self):
        super(DoubleStaircaseReinforced, self).next()

        if random.random() < self.probe_rate:
            try:
                ret = self.dblstaircase.next()
                self.last_probe = True
                return ret
            except StopIteration:
                self.probe_rate = 0
                self.last_probe = False
                return self.next()
        else:
            self.last_probe = False
            if random.random() < .5: # probe left
                if self.sample_log:
                    val = int((1 - rand_from_log_shape_dist()) * self.dblstaircase.low_idx)
                else:
                    val = random.randrange(self.dblstaircase.low_idx)
                return {'class': 'L',  'stim_name': self.stims[val]}
            else: # probe right
                if self.sample_log:
                    val = self.dblstaircase.high_idx + int(rand_from_log_shape_dist() * (len(self.stims) - self.dblstaircase.high_idx))
                else:
                    val = self.dblstaircase.high_idx + random.randrange(len(self.stims) - self.dblstaircase.high_idx)
                return {'class': 'R',  'stim_name': self.stims[val]}

    def no_response(self):
        super(DoubleStaircaseReinforced, self).no_response()
        self.last_probe = False

    def on_load(self):
        super(DoubleStaircaseReinforced, self).on_load()
        self.dblstaircase.on_load()


class MixedAdaptiveQueue(PersistentBase, AdaptiveBase):
    """
    Generates conditions from multiple adaptive sub queues.

    Use the generator MixedAdaptiveQueue.load(filename, sub_queues)
    to load a previously saved MixedAdaptiveQueue or generate a new one
    if the pkl file doesn't exist.

    sub_queues: a list of adaptive queues
    probabilities: a list of weights with which to sample from sub_queues
                        should be same length as sub_queues
                        NotImplemented
    filename: filename of pickle to save itself
    """
    def __init__(self, sub_queues, probabilities=None, **kwargs):
        super(MixedAdaptiveQueue, self).__init__(**kwargs)
        self.sub_queues = sub_queues
        self.probabilities = probabilities
        self.sub_queue_idx = -1
        self.update_error_str = "MixedAdaptiveQueue hasn't been updated since last trial"
        self.save()

    def update(self, correct, no_resp):
        super(MixedAdaptiveQueue, self).update(correct, no_resp)
        self.sub_queues[self.sub_queue_idx].update(correct, no_resp)
        self.save()

    def next(self):
        super(MixedAdaptiveQueue, self).next()
        if self.probabilities is None:
            try:
                self.sub_queue_idx = random.randrange(len(self.sub_queues))
                return self.sub_queues[self.sub_queue_idx].next()
            except StopIteration:
                #TODO: deal with subqueue finished, and possibility of all subqueues finishing
                raise NotImplementedError
        else:
            #TODO: support variable probabilities for each sub_queue
            raise NotImplementedError

    def on_load(self):
        super(MixedAdaptiveQueue, self).on_load()
        for sub_queue in self.sub_queues:
            try:
                sub_queue.on_load()
            except AttributeError:
                pass


class BaseHandler(object):
    """ Base class for implementing an iterable queue handler

    Parameters
    ----------
    queue: queue function or class
        The queue that will be iterated over. All queues must accept an items
        argument and implement generator, either through yielding values or a
        Class.next() method.
    items: list
        A list of items to iterate over.
    Additional key-value pairs are used to initialize the queue

    Attributes
    ----------
    queue: queue generator or class instance
        The queue that will be iterated over.
    queue_parameters: dict
        All additional parameters used to initialize the queue.        
    """

    def __init__(self, queue, items, **queue_parameters):

        if not hasattr(queue, "__call__"):
            raise TypeError("queue must be a callable function or class")
        # Store these in case we need to reset
        self._queue = queue
        self._items = items
        self.consumed = False

        self.queue = queue(items=items, **queue_parameters)
        self.queue_parameters = queue_parameters
        self._ondeck = next(self.queue)

    def reset(self):
        """ Reset the queue """
        self.consumed = False
        self.queue = self._queue(items=self._items, **self.queue_parameters)
        self._ondeck = next(self.queue)

    def __next__(self):
        if self._ondeck is None:
            raise StopIteration

        next_item = self._ondeck

        try:
            self._ondeck = next(self.queue)
        except StopIteration:
            self.consumed = True
            self._ondeck = None

        return next_item

    def next(self):
        return self.__next__()

    def __iter__(self):
        return self
