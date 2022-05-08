""" Testing TxPDOs with inhibt time """

from durand import Node, Variable, set_scheduler
from durand.scheduler import VirtualScheduler
from durand.datatypes import DatatypeEnum as DT

from ..adapter import MockAdapter, TxMsg, RxMsg


def test_local_config_inhibit():
    scheduler = VirtualScheduler()
    set_scheduler(scheduler)

    adapter = MockAdapter()

    # create the node
    node = Node(adapter, node_id=2)

    # add a variable with index 0x2000 to the object dictionary of the node
    node.object_dictionary[0x2000] = Variable(DT.INTEGER16, "rw", value=5)

    node.tpdo[0].mapping = [(0x2000, 0)]
    node.tpdo[0].inhibit_time = 0.5  # [s]

    # receive PDO message after changing into Operational state
    adapter.test(
        [   TxMsg(0x702, "00"),  # boot-up message from NMT

            RxMsg(0x000, "80 00"),  # set Pre-Operational state
            RxMsg(0x000, "01 00"),  # set Operational state

            TxMsg(0x182, "05 00")
        ]
    )

    # update the value and check, if PDO is sent (will be sent after 0.5s inhibit)
    node.object_dictionary.write(0x2000, 0, 0xAA)

    adapter.tx_mock.assert_not_called()

    scheduler.run(0.4)
    adapter.tx_mock.assert_not_called()

    scheduler.run(0.2)
    adapter.test(
        [   TxMsg(0x182, "AA 00")
        ]
    )

    scheduler.run(0.5)

    # update the value and check, if PDO is sent (will be sent immediatly)
    node.object_dictionary.write(0x2000, 0, 0xBB)

    adapter.test(
        [   TxMsg(0x182, "BB 00")
        ]
    )

    # read inhibt time via SDO
    adapter.test(
        [
            RxMsg(0x602, "40 00 18 03 00 00 00 00"),  # get inhibit time
            TxMsg(0x582, "4B 00 18 03 88 13 00 00"),  # receive 5000 [100µs]
        ]
    )


def test_remote_config_inhibit():
    scheduler = VirtualScheduler()
    set_scheduler(scheduler)

    adapter = MockAdapter()

    # create the node
    node = Node(adapter, node_id=2)

    # add a variable with index 0x2000 to the object dictionary of the node
    node.object_dictionary[0x2000] = Variable(DT.INTEGER16, "rw", value=5)

    node.tpdo[0].mapping = [(0x2000, 0)]

    adapter.test(
        [   TxMsg(0x702, "00"),  # boot-up message from NMT

            RxMsg(0x602, "2B 00 18 03 88 13 00 00"),  # set inhibit time to 5000 [100µs]
            TxMsg(0x582, "60 00 18 03 00 00 00 00"),  # response (acknowledge)

            RxMsg(0x000, "01 00"),  # set Operational state

            TxMsg(0x182, "05 00")
        ]
    )

    # update the value and change to NMT pre-operation state within inhibt time
    # PDO should not be sent
    node.object_dictionary.write(0x2000, 0, 0xAA)

    adapter.tx_mock.assert_not_called()

    scheduler.run(0.2)

    adapter.test(
        [   RxMsg(0x000, "80 00"),  # NMT go to pre-operational state
        ]
    )
    scheduler.run(1)

    adapter.tx_mock.assert_not_called()
