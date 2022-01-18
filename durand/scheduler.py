import asyncio
from sched import scheduler


class Scheduler:
    def __init__(self):
        self._loop = None

    @property
    def loop(self):
        return self._loop
    
    @loop.setter
    def loop(self, obj):
        assert self._loop is None, 'Loop already set'
        assert isinstance(obj, asyncio.AbstractEventLoop), 'Value has to be a abstract event loop'

        self._loop = obj
    
    def run(self):
        if self._loop:
            pass
        else:
            self._core = scheduler()
    
    def add(self, delay: float, callback, *args, **kwargs):
        self._core 