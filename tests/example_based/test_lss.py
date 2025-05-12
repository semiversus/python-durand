""" Testing LSS service """

from durand import Node, scheduler

from ..mock_network import MockNetwork, RxMsg, TxMsg


class MockScheduler(scheduler.AbstractScheduler):
    def add(self, delay: float, callback, args=(), kwargs=None) -> scheduler.TEntry:
        if kwargs is None:
            kwargs = {}
        callback(*args, **kwargs)

    def cancel(self, entry: scheduler.TEntry):
        ...

    @property
    def lock(self):
        ...


def test_global_selection():
    """Test example starts with a node with an undefined node id (0xFF).
    After the "switch state global" request to set every responder into configuration mode,
    the node id is set to 1.

    When switching back to waiting state via "switch state global" the node sends
    an boot up message (because the node id was undefined before).

    SDO requests are tested on node 1 to see, if the responder is responding.
    """
    network = MockNetwork()

    # create the node
    node = Node(network, node_id=0xFF)

    network.test(
        [
            RxMsg(
                0x7E5, "04 01 00 00 00 00 00 00"
            ),  # switch state global to configuration state
            RxMsg(0x7E5, "11 01 00 00 00 00 00 00"),  # set node id to 1
            TxMsg(0x7E4, "11 00 00 00 00 00 00 00"),  # receive the acknowledge
            RxMsg(
                0x601, "40 00 10 00 00 00 00 00"
            ),  # requesting via SDO on node 1 will still be unanswered
            RxMsg(
                0x7E5, "04 00 00 00 00 00 00 00"
            ),  # switch state global back to waiting state
            TxMsg(0x701, "00"),  # responder responses with Boot Up message
            RxMsg(0x601, "40 00 10 00 00 00 00 00"),  # requesting via SDO on node 1
            TxMsg(0x581, "43 00 10 00 00 00 00 00"),  # receive the acknowledge
        ]
    )


def test_configuration():
    """Test example starts with a node with node id 0x01.
    After the "switch state global" request to set every responder into configuration mode,
    the node id is set to 2.

    Furthermore, the baudrate is set to 500 kbit/s and the configuration is stored.
    When the configuration is stored, the node sends an acknowledge message.

    At last, activate bit timing is sent to the node. It is the responsibility of its callback
    to reinitialize the network with the new baudrate after a delay.
    The callback is tested with the baudrate and delay parameters.
    """

    scheduler_ = MockScheduler()
    scheduler.set_scheduler(scheduler_)

    network = MockNetwork()

    # create the node
    node = Node(network, node_id=0x01)

    def baudrate_change_callback(baudrate: int, delay: float):
        # This callback is supposed to reinitialize the network with the new baudrate
        # after the delay
        # In this test, we just check if the callback is called with the correct parameters
        assert baudrate == 500_000
        assert delay == 1

    node.lss.set_baudrate_change_callback(baudrate_change_callback)

    def store_configuration_callback(baudrate: int, node_id: int):
        assert baudrate == 500_000
        assert node_id == 2

    node.lss.set_store_configuration_callback(store_configuration_callback)

    network.test(
        [
            RxMsg(
                0x7E5, "04 01 00 00 00 00 00 00"
            ),  # switch state global to configuration state

            RxMsg(0x7E5, "11 02 00 00 00 00 00 00"),  # set node id to 2
            TxMsg(0x7E4, "11 00 00 00 00 00 00 00"),  # receive the acknowledge (success)

            RxMsg(0x7E5, "13 00 02 00 00 00 00 00"),  # set baudrate to 500 kbit/s
            TxMsg(0x7E4, "13 00 00 00 00 00 00 00"),  # receive the acknowledge (success)

            RxMsg(0x7E5, "17 00 00 00 00 00 00 00"),  # store configuration
            TxMsg(0x7E4, "17 00 00 00 00 00 00 00"),  # receive the acknowledge (success)

            RxMsg(0x7E5, "15 E8 03 00 00 00 00 00"),  # activate bit timing
        ]
    )
