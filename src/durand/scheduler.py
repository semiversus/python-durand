import asyncio
from abc import ABCMeta, abstractmethod
from dataclasses import dataclass
from typing import Callable, Tuple, TypeVar, Dict, Any, Generic
import functools
import threading
import sched


TEntry = TypeVar("TEntry")  # type of scheduler entry


class AbstractScheduler(Generic[TEntry], metaclass=ABCMeta):
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

    @property
    @abstractmethod
    def lock(self):
        """A global lock which can be used the assure thread safety"""
    
    def shutdown(self):
        """ Shutting down the scheduler """


class AsyncScheduler(AbstractScheduler):
    def __init__(self, loop=None):
        self._loop = loop

        self._lock = threading.Lock()

    def add(
        self, delay: float, callback, args=(), kwargs=None
    ) -> asyncio.TimerHandle:  # type: ignore[override]
        if kwargs:
            callback = functools.partial(callback, **kwargs)

        loop = self._loop or asyncio.get_event_loop()
        return loop.call_later(delay, callback, *args)

    def cancel(self, entry: asyncio.TimerHandle):  # type: ignore[override]
        entry.cancel()

    @property
    def lock(self):
        return self._lock
    
    # nothing happens at shutdown, as no resources have to be freed


class SyncScheduler(AbstractScheduler):
    def __init__(self, lock: threading.Lock = None):
        if lock is None:
            lock = threading.Lock()
        self._lock = lock
        self._sched = sched.scheduler()
        self._wake_up = threading.Event()
        self._stop = False

    def add(
        self, delay: float, callback, args=(), kwargs=None
    ) -> sched.Event:  # type: ignore[override]
        if kwargs is None:
            kwargs = {}
        self._wake_up.set()
        return self._sched.enter(delay, 0, callback, args, kwargs)

    def cancel(self, entry: sched.Event):  # type: ignore[override]
        self._sched.cancel(entry)

    def run(self):
        while True:
            self._sched.run()
            self._wake_up.wait()
            self._wake_up.clear()
            with self._lock:
                if self._stop:
                    break

    @property
    def lock(self):
        return self._lock
    
    def shutdown(self):
        self._wake_up.set()
        self._stop = True


class VirtualScheduler(AbstractScheduler):
    @dataclass
    class Entry:
        callback: Callable
        args: Tuple
        kwargs: Dict[str, Any]

    def __init__(self):
        self._time = 0
        self._lock = threading.Lock()
        self._entry_index = 1
        self._entry_dict: Dict[int, VirtualScheduler.Entry] = {}
        self._timestamp_dict: Dict[int, float] = {}

    def add(self, delay: float, callback, args=(), kwargs=None) -> int:  # type: ignore[override]
        if kwargs is None:
            kwargs = {}

        entry = VirtualScheduler.Entry(callback, args, kwargs)
        self._entry_dict[self._entry_index] = entry
        self._timestamp_dict[self._entry_index] = self._time + delay
        self._entry_index += 1
        return self._entry_index - 1

    def cancel(self, entry: int):  # type: ignore[override]
        self._entry_dict.pop(entry)
        self._timestamp_dict.pop(entry)

    def run(self, duration: float):
        start_time = self._time

        while self._entry_dict:
            earliest_timestamp = min(self._timestamp_dict.values())

            if earliest_timestamp > start_time + duration:
                break

            entry_indices = tuple(
                entry_index
                for entry_index, timestamp in self._timestamp_dict.items()
                if timestamp == earliest_timestamp
            )
            for entry_index in entry_indices:
                entry = self._entry_dict[entry_index]
                entry.callback(*entry.args, **entry.kwargs)
                self._entry_dict.pop(entry_index)
                self._timestamp_dict.pop(entry_index)

        self._time = start_time + duration

    @property
    def lock(self):
        return self._lock


class SchedulerProvider:
    def __init__(self):
        self._scheduler: AbstractScheduler = AsyncScheduler()

    def set(self, scheduler: AbstractScheduler) -> None:
        self._scheduler = scheduler

    def get(self) -> AbstractScheduler:
        return self._scheduler


scheduler_provider = SchedulerProvider()


def get_scheduler() -> AbstractScheduler:
    return scheduler_provider.get()


def set_scheduler(scheduler: AbstractScheduler):
    scheduler_provider.set(scheduler)
