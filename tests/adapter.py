from typing import Dict, Callable
from unittest.mock import Mock

from durand.adapters import AdapterABC


class MockAdapter(AdapterABC):
    def __init__(self):
        self.subscriptions = dict()
        self.tx_mock = Mock()

    def add_subscription(self, cob_id: int, callback):
        self.subscriptions[cob_id] = callback

    def remove_subscription(self, cob_id: int):
        self.subscriptions.pop(cob_id)

    def receive(self, cob_id: int, msg: bytes):
        """ Used in tests to send a CAN message to the node """
        print(f'RECV {cob_id:3X}: ' + ' '.join('%02X' % b for b in msg))
        self.subscriptions[cob_id](cob_id, msg)

    def send(self, cob_id: int, msg: bytes):
        """ When the node is sending a CAN message, it will be captured in .tx_mock """
        print(f'SEND {cob_id:3X}: ' + ' '.join('%02X' % b for b in msg))
        self.tx_mock(cob_id, msg)
        