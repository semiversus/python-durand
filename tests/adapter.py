from typing import List
from unittest.mock import Mock, call

from durand.adapters import AdapterABC


class Msg:
    def __init__(self, cob_id: int, *data):
        self.cob_id = cob_id

        self._data = b""
        for part in data:
            if isinstance(part, str):
                self._data += bytes.fromhex(part)
            elif isinstance(part, int):
                self._data += bytes([part])
            elif isinstance(part, bytes):
                self._data += part
            else:
                raise ValueError(
                    "Data parts have to be string containing hexcoded bytes, bytes or integers"
                )

        if len(self._data) > 8:
            raise ValueError("Maximum 8 bytes possible (%r)" % self._data)

    @property
    def data(self):
        return self._data

    def __eq__(self, msg: "Msg"):
        return self.cob_id == msg.cob_id and self._data == msg.data


class TxMsg(Msg):
    pass


class RxMsg(Msg):
    pass


class MockAdapter(AdapterABC):
    def __init__(self):
        self.subscriptions = dict()
        self.tx_mock = Mock()

    def add_subscription(self, cob_id: int, callback):
        self.subscriptions[cob_id] = callback

    def remove_subscription(self, cob_id: int):
        self.subscriptions.pop(cob_id)

    def receive(self, cob_id: int, msg: bytes):
        """Used in tests to send a CAN message to the node"""
        callback = self.subscriptions.get(cob_id, None)
        if callback is None:
            return
        callback(cob_id, msg)

    def send(self, cob_id: int, msg: bytes):
        """When the node is sending a CAN message, it will be captured in .tx_mock"""
        self.tx_mock(cob_id, msg)

    def test(self, messages: List[Msg]):
        tx_calls = list()

        for message in messages:
            if isinstance(message, RxMsg):
                self.tx_mock.assert_has_calls(tx_calls)
                self.tx_mock.reset_mock()
                tx_calls.clear()
                self.receive(message.cob_id, message.data)
            else:
                tx_calls.append(call(message.cob_id, message.data))

        self.tx_mock.assert_has_calls(tx_calls)
        assert self.tx_mock.call_count == len(tx_calls)

        self.tx_mock.reset_mock()
