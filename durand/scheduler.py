import asyncio
from abc import ABCMeta, abstractmethod, abstractproperty
from sched import scheduler
from typing import TypeVar
import functools
import threading


TEntry = TypeVar('TEntry')  # type of scheduler entry


class AbstractScheduler(metaclass=ABCMeta):
    @abstractmethod
    def add(self, delay: float, callback, args=(), kwargs={}) -> TEntry:
        """ Add a new scheduler entry.

        :param delay: time in seconds when the callback should be called
        :param callback: a function object called when time has passed
        :param args: tuple with positional arguments for the callback
        :param kwargs: dictionary with keyword arguments
        :returns: an id which can be used to cancel the scheduled callback
        """

    @abstractmethod
    def cancel(self, entry: TEntry):
        """ Cancel a scheduled callback

        :param entry: the scheduler entry to be canceld
        """

    def start(self):
        """ Start scheduling """

    @abstractproperty
    def lock(self):
        """ A global lock which can be used the assure thread safety """


class AsyncScheduler(AbstractScheduler):
    def __init__(self, loop=None):
        if loop is None:
            self._loop = asyncio.get_event_loop()
        else:
            self._loop = loop

        self._lock = threading.Lock()

    def add(self, delay: float, callback, args=(), kwargs=None) -> asyncio.TimerHandle:
        if kwargs:
            callback = functools.partial(callback, **kwargs)

        return self._loop.call_later(delay, callback, *args)

    def cancel(self, entry: asyncio.TimerHandle):
        entry.cancel()

    @property
    def lock(self):
        return self._lock


_scheduler = AsyncScheduler()


def get_scheduler() -> AbstractScheduler:
    return _scheduler


def set_scheduler(scheduler: AbstractScheduler):
    global _scheduler
    _scheduler = scheduler
