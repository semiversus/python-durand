""" Interfacing python-canopen-node with python-can library
"""
from typing import Dict, Callable

import can

from .base import AdapterABC


class CANAdapter(AdapterABC):
    def __init__(self, *args, loop=None, **kwargs):
        self._bus = can.Bus(*args, **kwargs)
        self._loop = loop

    def bind(self, subscriptions: Dict[int, Callable]):
        self._subscriptions = subscriptions
        listener = NodeListener(subscriptions)
        self.notifier = can.Notifier(self._bus, listener, 1, self._loop)

    def send(self, cob_id: int, msg: bytes):
        msg = can.Message(arbitration_id=cob_id, data=msg,
                          is_extended_id=False)
        self._bus.send(msg)


class NodeListener(can.Listener):
    def __init__(self, subscriptions: Dict[int, Callable]):
        self._subscriptions = subscriptions

    def on_message_received(self, msg: can.Message):
        if msg.is_error_frame or msg.is_remote_frame or msg.is_fd:
            # rtr is currently not supported
            return

        callback = self._subscriptions.get(msg.arbitration_id, None)

        if not callback:
            return

        callback(msg.arbitration_id, msg.data)
