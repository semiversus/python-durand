""" Testing TxPDOs with syned transmission type """

from durand import Node, Variable
from durand.datatypes import DatatypeEnum as DT

from ..adapter import MockAdapter, TxMsg, RxMsg


def test_local_config_sync():
    adapter = MockAdapter()

    # create the node
    node = Node(adapter, node_id=2)

    # add a variable with index 0x2000 to the object dictionary of the node
    node.object_dictionary[0x2000] = Variable(DT.INTEGER16, "rw", value=5)

    node.tpdo[0].mapping = [(0x2000, 0)]
    node.tpdo[0].transmission_type = 3

    # receive PDO message after changing into Operational state
    adapter.test(
        [   TxMsg(0x702, "00"),  # boot-up message from NMT

            RxMsg(0x000, "80 00"),  # set Pre-Operational state
            RxMsg(0x000, "01 00"),  # set Operational state

            RxMsg(0x80, ""),  # 1st SYNC
            RxMsg(0x80, ""),  # 2nd SYNC
            RxMsg(0x80, ""),  # 3rd SYNC

            TxMsg(0x182, "05 00")
        ]
    )

def test_remote_config_sync():
    adapter = MockAdapter()

    # create the node
    node = Node(adapter, node_id=2)

    # add a variable with index 0x2000 to the object dictionary of the node
    node.object_dictionary[0x2000] = Variable(DT.INTEGER16, "rw", value=5)

    node.tpdo[0].mapping = [(0x2000, 0)]

    # receive PDO message after changing into Operational state
    adapter.test(
        [   TxMsg(0x702, "00"),  # boot-up message from NMT

            RxMsg(0x602, "2F 00 18 02 00 00 00 00"),  # set transmission type to 0
            TxMsg(0x582, "60 00 18 02 00 00 00 00"),  # response (acknowledge)

            RxMsg(0x000, "80 00"),  # set Pre-Operational state
            RxMsg(0x000, "01 00"),  # set Operational state


            RxMsg(0x80, ""),  # sending a SYNC (without changed data)
            TxMsg(0x182, "05 00"),
            RxMsg(0x80, ""),  # sending another SYNC (without changed data)
        ]
    )

    assert node.tpdo[0].transmission_type == 0

    node.object_dictionary.write(0x2000, 0, 0xAA)
    adapter.test(
        [   RxMsg(0x80, ""),  # sending a SYNC
            TxMsg(0x182, "AA 00"),
            RxMsg(0x80, ""),  # sending another SYNC (without changed data)

            RxMsg(0x602, "2F 00 18 02 01 00 00 00"),  # set transmission type to 1
            TxMsg(0x582, "60 00 18 02 00 00 00 00"),  # response (acknowledge)

            RxMsg(0x80, ""),  # sending a SYNC
            TxMsg(0x182, "AA 00"),

            RxMsg(0x80, ""),  # sending a SYNC
            TxMsg(0x182, "AA 00"),
        ]
    )