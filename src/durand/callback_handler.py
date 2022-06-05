from enum import Enum
import logging
from typing import List, Callable


log = logging.getLogger(__name__)


class FailMode(Enum):
    IGNORE = 1  # exceptions are ignored
    FIRST_FAIL = (
        2  # first callback raising an exception will stop calling the following
    )
    LATE_FAIL = (
        3  # all callbacks will be called, but the first exception will be escalated
    )


class CallbackHandler:
    def __init__(self, fail_mode: FailMode = FailMode.IGNORE):
        self._callbacks: List[Callable] = []
        self._fail_mode = fail_mode

    def add(self, callback):
        self._callbacks.append(callback)

    def remove(self, callback):
        self._callbacks.remove(callback)

    def __contains__(self, callback):
        return callback in self._callbacks

    def call(self, *args, **kwargs):
        exception = None

        for callback in self._callbacks:
            try:
                callback(*args, **kwargs)
            except Exception as exc:
                if self._fail_mode == FailMode.LATE_FAIL and exception is None:
                    exception = exc
                elif self._fail_mode == FailMode.FIRST_FAIL:
                    raise exc
                else:
                    log.debug("Ignored exception in callback handler", exc_info=True)

        if exception:
            raise exception
