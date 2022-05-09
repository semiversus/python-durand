""" Testing EMCY messages """

from durand import Node

from ..adapter import MockAdapter, TxMsg


def test_simple_emcy():
    adapter = MockAdapter()

    # create the node
    node = Node(adapter, node_id=2)

    adapter.tx_mock.reset_mock()

    node.emcy.set(0x1000, 1, data=b'\xAA')
    node.emcy.set(0, 0)

    # receive EMCY message
    adapter.test([
            TxMsg(0x82, "00 10 01 AA 00 00 00 00"),  # receive EMCY with 0x1000 error code
            TxMsg(0x82, "00 00 00 00 00 00 00 00")  # receive reset of EMCY
        ]
    )
