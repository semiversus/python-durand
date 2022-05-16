""" Interfacing python-canopen-node with python-can library
"""
from typing import Dict, Callable
from threading import Lock

import can

from .base import AdapterABC


class CANAdapter(AdapterABC):
    def __init__(self, *args, loop=None, **kwargs):
        self._bus = can.Bus(*args, **kwargs)
        self._loop = loop

        self.lock = Lock()
        self.subscriptions = dict()

        listener = NodeListener(self)
        can.Notifier(self._bus, (listener,), 1, self._loop)

    def add_subscription(self, cob_id: int, callback):
        with self.lock:
            self.subscriptions[cob_id] = callback
            self._update_filters()

    def remove_subscription(self, cob_id: int):
        with self.lock:
            self.subscriptions.pop(cob_id)
            self._update_filters()

    def _update_filters(self):
        self._bus.set_filters(
            [{"can_id": i, "can_mask": 0x7FF} for i in self.subscriptions]
        )

    def send(self, cob_id: int, msg: bytes):
        msg = can.Message(arbitration_id=cob_id, data=msg, is_extended_id=False)
        self._bus.send(msg)


class NodeListener(can.Listener):
    def __init__(self, adapter: CANAdapter):
        self._adapter = adapter

    def on_message_received(self, msg: can.Message):
        if msg.is_error_frame or msg.is_remote_frame or msg.is_fd:
            # rtr is currently not supported
            return

        with self._adapter.lock:
            callback = self._adapter.subscriptions.get(msg.arbitration_id, None)

        if not callback:
            return

        callback(msg.arbitration_id, msg.data)
