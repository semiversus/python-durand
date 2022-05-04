""" Testing additional SDO servers. """
from durand import Node

from ..adapter import MockAdapter, TxMsg, RxMsg


def test_remote_configure():
    """In this example an additional SDO server is remotly configured (via CAN bus)"""
    adapter = MockAdapter()

    # create the node
    node = Node(adapter, node_id=2)

    # setup sdo server 9 (rx cob: 0x640, tx_cob: 0x5c0, remote node id: 1)
    adapter.test(
        [
            RxMsg(0x602, "23 09 12 01 40 06 00 00"),  # set rx cob to 0x640
            TxMsg(0x582, "60 09 12 01 00 00 00 00"),  # receive the acknowledge
            RxMsg(0x602, "23 09 12 02 c0 05 00 00"),  # set tx cob to 0x5c0
            TxMsg(0x582, "60 09 12 02 00 00 00 00"),  # receive the acknowledge
            RxMsg(0x602, "2F 09 12 03 01 00 00 00"),  # set client node id to 1
            TxMsg(0x582, "60 09 12 03 00 00 00 00"),  # receive the acknowledge
        ]
    )

    # download object 0x1000 via SDO using SDO server 9
    adapter.test(
        [
            RxMsg(0x640, "40 00 10 00 00 00 00 00"),  # request
            TxMsg(0x5C0, "43 00 10 00 00 00 00 00"),  # response
        ]
    )

    # check if attributes are updated
    assert node.sdo_servers[9].cob_rx == 0x640
    assert node.sdo_servers[9].cob_tx == 0x5C0
    assert node.sdo_servers[9].client_node_id == 1


def test_local_configure():
    """Configuring the additional SDO server local via attributes of the SDO
    server object
    """
    adapter = MockAdapter()

    # create the node
    node = Node(adapter, node_id=2)

    # setup sdo server 9 (rx cob: 0x640, tx_cob: 0x5c0, remote node id: 1)
    node.sdo_servers[9].cob_rx = 0x640
    node.sdo_servers[9].cob_tx = 0x5C0
    node.sdo_servers[9].client_node_id = 1

    # download object 0x1000 via SDO using SDO server 9
    adapter.test(
        [
            RxMsg(0x640, "40 00 10 00 00 00 00 00"),  # request
            TxMsg(0x5C0, "43 00 10 00 00 00 00 00"),  # response
        ]
    )

    # check if object dictionary is updated
    adapter.test(
        [
            RxMsg(0x602, "40 09 12 01 00 00 00 00"),  # get rx cob
            TxMsg(0x582, "43 09 12 01 40 06 00 00"),  # receive 0x640
            RxMsg(0x602, "40 09 12 02 00 00 00 00"),  # get tx cob
            TxMsg(0x582, "43 09 12 02 c0 05 00 00"),  # receive 0x5c0
            RxMsg(0x602, "40 09 12 03 00 00 00 00"),  # get client node id
            TxMsg(0x582, "4F 09 12 03 01 00 00 00"),  # receive 1
        ]
    )
