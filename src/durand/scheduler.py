import asyncio
from abc import ABCMeta, abstractmethod, abstractproperty
from dataclasses import dataclass
from typing import Callable, Tuple, TypeVar, Dict, Any
import functools
import threading
from sched import scheduler


TEntry = TypeVar("TEntry")  # type of scheduler entry


class AbstractScheduler(metaclass=ABCMeta):
    @abstractmethod
    def add(self, delay: float, callback, args=(), kwargs=None) -> TEntry:
        """Add a new scheduler entry.

        :param delay: time in seconds when the callback should be called
        :param callback: a function object called when time has passed
        :param args: tuple with positional arguments for the callback
        :param kwargs: dictionary with keyword arguments
        :returns: an id which can be used to cancel the scheduled callback
        """

    @abstractmethod
    def cancel(self, entry: TEntry):
        """Cancel a scheduled callback

        :param entry: the scheduler entry to be canceled
        """

    @abstractproperty
    def lock(self):
        """A global lock which can be used the assure thread safety"""


class AsyncScheduler(AbstractScheduler):
    def __init__(self, loop=None):
        self._loop = loop

        self._lock = threading.Lock()

    def add(self, delay: float, callback, args=(), kwargs=None) -> asyncio.TimerHandle:
        if kwargs:
            callback = functools.partial(callback, **kwargs)

        loop = self._loop or asyncio.get_event_loop()
        return loop.call_later(delay, callback, *args)

    def cancel(self, entry: asyncio.TimerHandle):
        entry.cancel()

    @property
    def lock(self):
        return self._lock


class SyncScheduler(AbstractScheduler):
    def __init__(self, lock: threading.Lock=None):
        if lock is None:
            lock = threading.Lock()
        self._lock = lock
        self._sched = scheduler()
        self._wake_up = threading.Event()

    def add(self, delay: float, callback, args=(), kwargs=None) -> asyncio.TimerHandle:
        if kwargs == None:
            kwargs = {}
        self._wake_up.set()
        return self._sched.enter(delay, 0, callback, args, kwargs)

    def cancel(self, entry):
        self._sched.cancel(entry)

    def run(self):
        while True:
            self._sched.run()
            self._wake_up.wait()
            self._wake_up.clear()

    @property
    def lock(self):
        return self._lock


class VirtualScheduler(AbstractScheduler):
    @dataclass
    class Entry:
        callback: Callable
        args: Tuple
        kwargs: Dict[str, Any]

    def __init__(self):
        self._time = 0
        self._lock = threading.Lock()
        self._id = 1
        self._entry_dict: Dict[int, VirtualScheduler.Entry] = dict()
        self._timestamp_dict: Dict[int, float] = dict()

    def add(self, delay: float, callback, args=(), kwargs=None) -> TEntry:
        if kwargs is None:
            kwargs = {}

        entry = VirtualScheduler.Entry(callback, args, kwargs)
        self._entry_dict[self._id] = entry
        self._timestamp_dict[self._id] = self._time + delay
        self._id += 1
        return self._id - 1

    def cancel(self, entry: int):
        self._entry_dict.pop(entry)
        self._timestamp_dict.pop(entry)

    def run(self, duration: float):
        start_time = self._time

        while self._entry_dict:
            earliest_timestamp = min(self._timestamp_dict.values())

            if earliest_timestamp > start_time + duration:
                break

            ids = tuple(
                id
                for id, timestamp in self._timestamp_dict.items()
                if timestamp == earliest_timestamp
            )
            for id in ids:
                entry = self._entry_dict[id]
                entry.callback(*entry.args, **entry.kwargs)
                self._entry_dict.pop(id)
                self._timestamp_dict.pop(id)

        self._time = start_time + duration

    @property
    def lock(self):
        return self._lock


_scheduler = AsyncScheduler()


def get_scheduler() -> AbstractScheduler:
    return _scheduler


def set_scheduler(scheduler: AbstractScheduler):
    global _scheduler
    _scheduler = scheduler
