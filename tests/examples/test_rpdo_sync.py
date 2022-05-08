""" Testing RxPDOs with syncing """

from durand import Node, Variable
from durand.datatypes import DatatypeEnum as DT

from ..adapter import MockAdapter, TxMsg, RxMsg


def test_rpdo_sync():
    adapter = MockAdapter()

    # create the node
    node = Node(adapter, node_id=2)

    # add a variable with index 0x2000 to the object dictionary of the node
    node.object_dictionary[0x2000] = Variable(DT.INTEGER16, "rw", value=5)

    # receive PDO message after changing into Operational state
    adapter.test(
        [   TxMsg(0x702, "00"),  # boot-up message from NMT

            RxMsg(0x602, "2F 00 14 02 00 00 00 00"),  # set transmission type to 0
            TxMsg(0x582, "60 00 14 02 00 00 00 00"),  # response (acknowledge)

            RxMsg(0x602, "23 00 16 01 02 00 00 20"),  # set mapping of 0x2000:0
            TxMsg(0x582, "60 00 16 01 00 00 00 00"),  # response (acknowledge)

            RxMsg(0x602, "2F 00 16 00 01 00 00 00"),  # set mapping length to 1
            TxMsg(0x582, "60 00 16 00 00 00 00 00"),  # response (acknowledge)

            RxMsg(0x000, "80 00"),  # set NMT Pre-Operational state
            RxMsg(0x000, "01 00"),  # set NMT Operational state

            RxMsg(0x202, "02 00")  # receive the PDO message (will be ignored until sync)
        ]
    )

    assert node.object_dictionary.read(0x2000, 0) == 5

    adapter.test(
        [  
            RxMsg(0x80, "")  # receive sync message
        ]
    )

    assert node.object_dictionary.read(0x2000, 0) == 2
