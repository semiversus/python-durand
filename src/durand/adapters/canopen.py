""" Interfacing python-canopen-node with python-canopen
"""
from typing import Dict, Callable

from canopen import Network
from .base import AdapterABC


class CANopenAdapter(AdapterABC):
    def __init__(self, network: Network):
        self._network = network
        self._subscriptions = dict()

    def add_subscription(self, cob_id: int, callback):
        self._subscriptions[cob_id] = callback
        self._network.subscribe(cob_id, callback)

    def remove_subscription(self, cob_id: int):
        callback = self._subscriptions.pop(cob_id)
        self._network.unsubscribe(cob_id, callback)

    def send(self, cob_id: int, msg: bytes):
        self._network.notify(cob_id, msg)
