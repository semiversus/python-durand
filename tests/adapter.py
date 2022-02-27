from typing import Dict, Callable
from unittest.mock import Mock

from durand.adapters import AdapterABC


class MockAdapter(AdapterABC):
    def __init__(self):
        self._subscriptions = None
        self.tx_mock = Mock()

    def bind(self, subscriptions: Dict[int, Callable]):
        self._subscriptions = subscriptions

    def receive(self, cob_id: int, msg: bytes):
        """ Used in tests to send a CAN message to the node """
        self._subscriptions[cob_id](cob_id, msg)

    def send(self, cob_id: int, msg: bytes):
        """ When the node is sending a CAN message, it will be captured in .tx_mock """
        self.tx_mock(cob_id, msg)
