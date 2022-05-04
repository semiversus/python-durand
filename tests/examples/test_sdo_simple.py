""" Up- and download of objects via SDO server """

from durand import Node, Variable
from durand.datatypes import DatatypeEnum as DT

from ..adapter import MockAdapter, TxMsg, RxMsg


def test_simple_access():
    adapter = MockAdapter()

    # create the node
    node = Node(adapter, node_id=2)

    # add a variable with index 0x2000:0 to the object dictionary of the node
    node.object_dictionary[0x2000] = Variable(DT.INTEGER16, "rw", value=5)

    # upload the value 1 via SDO
    adapter.test(
        [
            RxMsg(
                0x602, "2b 00 20 00 01 00 00 00"
            ),  # send the upload request with value 1
            TxMsg(0x582, "60 00 20 00 00 00 00 00"),  # receive the acknowledge
        ]
    )

    # download object via SDO
    adapter.test(
        [
            RxMsg(0x602, "40 00 20 00 00 00 00 00"),  # send the download request
            TxMsg(0x582, "4b 00 20 00 01 00 00 00"),  # received the value 1
        ]
    )


def test_nmt_state():
    """The SDO server is only active when node is in pre-operational or operational state"""
    adapter = MockAdapter()

    # create the node
    node = Node(adapter, node_id=2)

    # TODO
