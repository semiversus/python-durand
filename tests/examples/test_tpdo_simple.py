""" Testing TxPDOs """

from durand import Node, Variable
from durand.datatypes import DatatypeEnum as DT

from ..adapter import MockAdapter, TxMsg, RxMsg


def test_local_config_tpdo():
    adapter = MockAdapter()

    # create the node
    node = Node(adapter, node_id=2)

    # add a variable with index 0x2000 to the object dictionary of the node
    node.object_dictionary[0x2000] = Variable(DT.INTEGER16, "rw", value=5)

    node.tpdo[0].mapping = [(0x2000, 0)]

    # send PDO message after changing into Operational state
    adapter.test(
        [   TxMsg(0x702, "00"),  # boot-up message from NMT

            RxMsg(0x000, "80 00"),  # set Pre-Operational state
            RxMsg(0x000, "01 00"),  # set Operational state

            TxMsg(0x182, "05 00")
        ]
    )

    # update the value and check, if PDO is sent
    node.object_dictionary.write(0x2000, 0, 0xAA)

    adapter.test(
        [   TxMsg(0x182, "AA 00")
        ]
    )

    # check PDO configuration via SDO
    adapter.test(
        [
            RxMsg(0x602, "40 00 18 01 00 00 00 00"),  # get cob id for sending
            TxMsg(0x582, "43 00 18 01 82 01 00 40"),  # receive 0x4000_0182
            RxMsg(0x602, "40 00 18 02 00 00 00 00"),  # get transmission type
            TxMsg(0x582, "4F 00 18 02 FF 00 00 00"),  # receive 0xFF
        ]
    )

    # disable PDO
    node.tpdo[0].enable = False

    node.object_dictionary.write(0x2000, 0, 0xBB)  # this will not trigger a PDO

    adapter.test(
        [
            RxMsg(0x602, "40 00 18 01 00 00 00 00"),  # get cob id for sending
            TxMsg(0x582, "43 00 18 01 82 01 00 C0"),  # receive 0xC000_0182
        ]
    )

def test_remote_config_tpdo():
    adapter = MockAdapter()

    # create the node
    node = Node(adapter, node_id=2)

    # add a variable with index 0x2000 to the object dictionary of the node
    node.object_dictionary[0x2000] = Variable(DT.INTEGER16, "rw", value=5)

    assert node.tpdo[10].enable == False

    adapter.test(
        [   TxMsg(0x702, "00"),  # boot-up message from NMT

            RxMsg(0x602, "23 0A 1A 01 02 00 00 20"),  # map object 0x2000 to PDO 11
            TxMsg(0x582, "60 0A 1A 01 00 00 00 00"),  # response (acknowledge)

            RxMsg(0x602, "2F 0A 1A 00 01 00 00 00"),  # set number of mapped objects to 1
            TxMsg(0x582, "60 0A 1A 00 00 00 00 00"),  # response (acknowledge)

            RxMsg(0x602, "23 0A 18 01 00 02 00 40"),  # set cob id to 0x200 (and enable)
            TxMsg(0x582, "60 0A 18 01 00 00 00 00"),  # response (acknowledge)

            RxMsg(0x000, "01 00"),  # set Operational state

            TxMsg(0x200, "05 00")
        ]
    )

    assert node.tpdo[10].enable == True
    assert node.tpdo[10].mapping == ((0x2000, 0),)