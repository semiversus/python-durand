""" Interfacing python-canopen-node with python-can library
"""
from abc import ABCMeta, abstractmethod
from threading import Lock

import can


class NetworkABC(metaclass=ABCMeta):
    @abstractmethod
    def add_subscription(self, cob_id: int, callback):
        """add subscription
        :param cob_id: cob_id to subscribe
        :param callback: to be called when cob_id is received
        """

    @abstractmethod
    def remove_subscription(self, cob_id: int):
        """remove subscription
        :param cob_id: remove subscription for cob_id
        """

    @abstractmethod
    def send(self, cob_id: int, msg: bytes):
        """sending a CAN message to the network
        :param cob_id: CAN arbitration id
        :param msg: CAN data bytes
        """


class CANBusNetwork(NetworkABC):
    def __init__(self, can_bus: can.BusABC, loop=None):
        self._bus = can_bus
        self._loop = loop

        self.lock = Lock()
        self.subscriptions = {}

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
    def __init__(self, network: CANBusNetwork):
        self._network = network

    def on_message_received(self, msg: can.Message):
        if msg.is_error_frame or msg.is_remote_frame or msg.is_fd:
            # rtr is currently not supported
            return

        with self._network.lock:
            callback = self._network.subscriptions.get(msg.arbitration_id, None)

        if not callback:
            return

        callback(msg.arbitration_id, msg.data)
