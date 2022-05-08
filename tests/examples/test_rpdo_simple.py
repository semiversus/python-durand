""" Testing RxPDOs """

from durand import Node, Variable
from durand.datatypes import DatatypeEnum as DT

from ..adapter import MockAdapter, TxMsg, RxMsg


def test_local_config_rpdo():
    adapter = MockAdapter()

    # create the node
    node = Node(adapter, node_id=2)

    # add a variable with index 0x2000 to the object dictionary of the node
    node.object_dictionary[0x2000] = Variable(DT.INTEGER16, "rw", value=5)

    node.rpdo[0].mapping = [(0x2000, 0)]

    # receive PDO message after changing into Operational state
    adapter.test(
        [   TxMsg(0x702, "00"),  # boot-up message from NMT

            RxMsg(0x000, "80 00"),  # set NMT Pre-Operational state
            RxMsg(0x202, "02 00")  # receive the PDO message (will be ignored)
        ]
    )

    assert node.object_dictionary.read(0x2000, 0) == 5

    adapter.test(
        [  
            RxMsg(0x000, "01 00"),  # set NMT Operational state

            RxMsg(0x202, "02 00")  # receive the PDO message
        ]
    )

    assert node.object_dictionary.read(0x2000, 0) == 2

    # check PDO configuration via SDO
    adapter.test(
        [
            RxMsg(0x602, "40 00 14 01 00 00 00 00"),  # get cob id for sending
            TxMsg(0x582, "43 00 14 01 02 02 00 00"),  # receive 0x0000_0202
            RxMsg(0x602, "40 00 14 02 00 00 00 00"),  # get transmission type
            TxMsg(0x582, "4F 00 14 02 FF 00 00 00"),  # receive 0xFF
        ]
    )

    # disable PDO
    node.rpdo[0].enable = False

    adapter.test([RxMsg(0x202, "01 00")])  # receive the PDO message
    
    assert node.object_dictionary.read(0x2000, 0) == 2
    
    adapter.test(
        [
            RxMsg(0x602, "40 00 14 01 00 00 00 00"),  # get cob id for sending
            TxMsg(0x582, "43 00 14 01 02 02 00 80"),  # receive 0x8000_0202
        ]
    )
