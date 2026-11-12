""" Testing NMT service """

from durand import Node

from ..mock_network import MockNetwork


def test_sdo_server_ready_at_bootup():
    """A master may send an SDO request right after receiving the boot-up message.
    The SDO server has to be subscribed already when the boot-up message is sent.
    """
    network = MockNetwork()
    node = Node(network, node_id=0x0E)
    node.nmt.pending_node_id = 0x0A

    sdo_reachable_at_bootup = []

    def send(cob_id: int, msg: bytes):
        if cob_id == 0x70A:
            sdo_reachable_at_bootup.append(0x60A in network.subscriptions)

    network.send = send

    network.receive(0, b"\x81\x0E")  # NMT reset node

    assert sdo_reachable_at_bootup == [True]
