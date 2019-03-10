import logging

import numpy as np

from pyoperant import queues, reinf, utils, trials


logger = logging.getLogger(__name__)


class Block(queues.BaseHandler):
    """ Class that allows one to iterate over a block of trials according to a
    specific queue.

    Parameters
    ----------
    conditions: list
        A list of StimulusConditions to iterate over according to the queue
    index: int
        Index of the block
    experiment: instance of Experiment class
        The experiment of which this block is a part
    queue: a queue function or Class
        The queue used to iterate over trials for this block
    reinforcement: instance of Reinforcement class (ContinuousReinforcement())
        The reinforcement schedule to use for this block.
    Additional key-value pairs are used to initialize the trial queue

    Attributes
    ----------
    conditions: list
        A list of StimulusConditions to iterate over according to the queue
    index: int
        Index of the block
    experiment: instance of Experiment class
        The experiment of which this block is a part
    queue: queue generator or class instance
        The queue that will be iterated over.
    reinforcement: instance of Reinforcement class (ContinuousReinforcement())
        The reinforcement schedule to use for this block.
    consumed: boolean indicating whether the underlying queue has been fully
        consumed

    Examples
    --------
    # Initialize a block with a random queue, and at most 200 trials.
    trials = Block(conditions,
                   experiment=e,
                   queue=queues.random_queue,
                   max_items=200)
    for trial in trials:
        trial.run()
    """

    def __init__(self, conditions, index=0, experiment=None,
                 queue=queues.random_queue, reinforcement=None,
                 **queue_parameters):

        if conditions is None:
            raise ValueError("Block must be called with a list of conditions")

        # Could check to ensure reinforcement is of the correct type
        if reinforcement is None:
            reinforcement = reinf.ContinuousReinforcement()

        super(Block, self).__init__(queue=queue,
                                    items=conditions,
                                    **queue_parameters)

        self.index = index
        self.experiment = experiment
        self.conditions = conditions
        self.reinforcement = reinforcement

        logger.debug("Initialize block: %s" % self)

    def __str__(self):
        desc = ["Block"]
        if self.conditions is not None:
            desc.append("%d stimulus conditions" % len(self.conditions))
        if self.queue is not None:
            desc.append("queue = %s" % self.queue.__name__)

        return " - ".join(desc)

    def check_completion(self):
        return self.consumed

    def next_trial(self):
        return next(self)

    def __next__(self):
        condition = super(Block, self).__next__()

        # if self._trial is None or not self._trial.aborted:
        self._trial_index += 1

        self._trial = trials.Trial(index=self._trial_index,
                             experiment=self.experiment,
                             condition=condition,
                             block=self)
        return self._trial

    def next(self):
        """For python 2 compatibility with the next() function"""
        return self.__next__()

    def __iter__(self):
        # Loop through the queue generator
        self._trial_index = 0
        self._trial = None

        return self


class BlockHandler(queues.BaseHandler):
    """ Class which enables iterating over blocks of trials

    Parameters
    ----------
    blocks: list
        A list of Block objects
    queue: a queue function or Class
        The queue used to iterate over blocks
    Additional key-value pairs are used to initialize the queue

    Attributes
    ----------
    block_index: int
        Index of the current block
    blocks: list
        A list of Block objects
    queue: queue generator or class instance
        The queue that will be iterated over.
    queue_parameters: dict
        All additional parameters used to initialize the queue.

    Example
    -------
    # Initialize the BlockHandler
    blocks = BlockHandler(blocks, queue=queues.block_queue)
    # Loop through the blocks, then loop through all trials in the block
    for block in blocks:
        for trial in block:
            trial.run()
    """

    def __init__(self, blocks, queue=queues.block_queue, **queue_parameters):
        self.blocks = blocks
        self.block_index = 0
        super(BlockHandler, self).__init__(queue=queue,
                                           items=blocks,
                                           **queue_parameters)

    def __next__(self):
        block = super(BlockHandler, self).__next__()
        self.block_index += 1
        block.index = self.block_index
        return block

    def __iter__(self):
        return self


class MixedBlockHandler(BlockHandler):
    """Switching between a triggered and autoplaying block

    Parameters
    ----------
    **kwargs:
        Mapping of block name to block. The block must allow for manual
        iteration through the next() function and the ability to
        be reset()

    Attributes
    ----------
    blocks: list of blocks.Block objects
    _iters: dictionary mapping block name to block iterator
        (over uncompleted trials)
    """

    def __init__(self, **kwargs):
        self.blocks = kwargs
        self.reset()

    def reset(self):
        """Reset blocks and iterators

        Parameters
        ----------
        block_name: str
            Name of the block to reset. If None, reset all blocks.
        """
        self._iters = dict(
            (block_name, iter(block))
            for block_name, block in self.blocks.items()
        )

        for block in self.blocks.values():
            block.reset()

        self._trial_index = 0

    def check_completion(self, block_name=None):
        """Check for block completion

        Use block_name to check a single block, or
        leave as None to check if all blocks are complete
        """
        if block_name is not None:
            return self.blocks[block_name].check_completion()
        else:
            return np.all([
                block.check_completion() for block in self.blocks.values()
            ])

    def reset_one(self, block_name):
        block = self.blocks[block_name]
        self._iters[block_name] = iter(block)
        block.reset()

    def next_trial(self, block_name):
        """Get next trial by block name and increment trial index
        """
        self._trial_index += 1
        trial = next(self._iters[block_name])
        trial.index = self._trial_index

        return trial
