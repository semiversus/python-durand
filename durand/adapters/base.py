from abc import ABCMeta, abstractmethod
from typing import Dict, Callable


class AdapterABC(metaclass=ABCMeta):
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
        """sending a CAN message to the adapter
        :param cob_id: CAN arbitration id
        :param msg: CAN data bytes
        """
