from abc import ABCMeta, abstractmethod
from typing import Dict, Callable


class AdapterABC(metaclass=ABCMeta):
    @abstractmethod
    def bind(self, subscriptions: Dict[int, Callable]):
        """ Use subscription dictionary to distribute CAN messages
        to the according callback

        :param subscriptions: dictionary for with COB ID as key and callback as
                              value
        """

    @abstractmethod
    def send(self, cob_id: int, msg: bytes):
        """ sending a CAN message to the adapter
        :param cob_id: CAN arbitration id
        :param msg: CAN data bytes
        """
