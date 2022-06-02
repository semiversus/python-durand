""" Testing EMCY messages """

from durand import Node

from ..mock_network import MockNetwork, TxMsg


def test_simple_emcy():
    network = MockNetwork()

    # create the node
    node = Node(network, node_id=2)

    network.tx_mock.reset_mock()

    node.emcy.set(0x1000, 1, data=b'\xAA')
    node.emcy.set(0, 0)

    # receive EMCY message
    network.test([
            TxMsg(0x82, "00 10 01 AA 00 00 00 00"),  # receive EMCY with 0x1000 error code
            TxMsg(0x82, "00 00 00 00 00 00 00 00")  # receive reset of EMCY
        ]
    )
