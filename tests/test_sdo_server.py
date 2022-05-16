import struct

import pytest

from durand import Node, Variable
from durand.datatypes import DatatypeEnum as DT

from .adapter import MockAdapter, TxMsg, RxMsg


@pytest.mark.parametrize("node_id", [0x01, 0x7F])
def test_sdo_object_dictionary(node_id):
    n = Node(MockAdapter(), node_id)

    assert n.object_dictionary.lookup(0x1200, 0) == Variable(
        DT.UNSIGNED8, "const", value=2, name='Highest Sub-Index Supported'
    )
    assert n.object_dictionary.lookup(0x1200, 1) == Variable(
        DT.UNSIGNED32, "ro", value=0x600 + node_id, name='COB-ID Client->Server (rx)'
    )
    assert n.object_dictionary.lookup(0x1200, 2) == Variable(
        DT.UNSIGNED32, "ro", value=0x580 + node_id, name='COB-ID Server -> Client (tx)'
    )

    with pytest.raises(KeyError):
        n.object_dictionary.lookup(0x1200, 3)


@pytest.mark.parametrize("node_id", [0x01, 0x7F])
@pytest.mark.parametrize("index", [1, 2, 127])
def test_sdo_additional_servers(node_id, index):
    n = Node(MockAdapter(), node_id)

    assert n.object_dictionary.lookup(0x1200 + index, 0) == Variable(
        DT.UNSIGNED8, "const", value=3, name='Highest Sub-Index Supported'
    )
    assert n.object_dictionary.lookup(0x1200 + index, 1) == Variable(
        DT.UNSIGNED32, "rw", value=0x8000_0000, name='COB-ID Client->Server (rx)'
    )
    assert n.object_dictionary.lookup(0x1200 + index, 2) == Variable(
        DT.UNSIGNED32, "rw", value=0x8000_0000, name='COB-ID Server -> Client (tx)'
    )
    assert n.object_dictionary.lookup(0x1200 + index, 3) == Variable(DT.UNSIGNED8, "rw", name='Node-ID of the SDO Client')


@pytest.mark.parametrize("sdo_server", [1, 127])
@pytest.mark.parametrize("node_id", [0x01, 0x7F])
def test_config_sdo_server(node_id, sdo_server):
    adapter = MockAdapter()

    n = Node(adapter, node_id)

    adapter.test(
        [
            RxMsg(
                0x640, "40 00 12 00 00 00 00 00"
            ),  # cob_id 640h should be ignored (will be used later)
            RxMsg(
                0x600 + node_id, "40", sdo_server, "12 01 00 00 00 00"
            ),  # read sdo server rx cob id
            TxMsg(
                0x580 + node_id, "43", sdo_server, "12 01 00 00 00 80"
            ),  # should be 0x8000_0000
        ]
    )

    assert n.sdo_servers[sdo_server].cob_rx is None
    assert n.sdo_servers[sdo_server].cob_tx is None

    adapter.test(
        [
            # set rx cob of sdo server to 0x640
            RxMsg(
                0x600 + node_id, "23", sdo_server, "12 01 40 06 00 00"
            ),  # set sdo server rx cob id to 0x640
            TxMsg(
                0x580 + node_id, "60", sdo_server, "12 01 00 00 00 00"
            ),  # acknowledge
            RxMsg(
                0x640, "40 00 12 00 00 00 00 00"
            ),  # cob_id 640h should still be ignored
        ]
    )

    assert n.sdo_servers[sdo_server].cob_rx == 0x640
    assert n.sdo_servers[sdo_server].cob_tx is None

    adapter.test(
        [
            # set tx cob of sdo server to 0x5C0
            RxMsg(
                0x600 + node_id, "23", sdo_server, "12 02 C0 05 00 00"
            ),  # set sdo server tx cob id to 0x5C0
            TxMsg(
                0x580 + node_id, "60", sdo_server, "12 02 00 00 00 00"
            ),  # acknowledge
            # check sdo server
            RxMsg(
                0x640, "40 00 12 00 00 00 00 00"
            ),  # cob_id 640h should now work (read number of subindex in object 0x1200)
            TxMsg(
                0x5C0, "4F 00 12 00 02 00 00 00"
            ),  # response with number of subindex (3)
        ]
    )

    assert n.sdo_servers[sdo_server].cob_rx == 0x640
    assert n.sdo_servers[sdo_server].cob_tx == 0x5C0

    # set tx cob of sdo server to 0x5D0
    n.sdo_servers[sdo_server].cob_tx = 0x5D0

    adapter.test(
        [
            RxMsg(
                0x640, "40 00 12 00 00 00 00 00"
            ),  # cob_id 640h should now work (read number of subindex in object 0x1200)
            TxMsg(
                0x5D0, "4F 00 12 00 02 00 00 00"
            ),  # response with number of subindex (3)
        ]
    )

    assert n.sdo_servers[sdo_server].cob_rx == 0x640
    assert n.sdo_servers[sdo_server].cob_tx == 0x5D0

    adapter.test(
        [
            # disable rx of sdo server
            RxMsg(
                0x600 + node_id, "23", sdo_server, "12 01 00 00 00 80"
            ),  # set sdo server rx cob id to 0x8000_0000
            TxMsg(
                0x580 + node_id, "60", sdo_server, "12 01 00 00 00 00"
            ),  # acknowledge
            RxMsg(
                0x640, "40 00 12 00 00 00 00 00"
            ),  # cob_id 640h should now be ignored
        ]
    )

    assert n.sdo_servers[sdo_server].cob_rx is None

    adapter.test(
        [
            # re-enable rx of sdo server and set to 0x641
            RxMsg(
                0x600 + node_id, "23", sdo_server, "12 01 41 06 00 00"
            ),  # set sdo server rx cob id to 0x641
            TxMsg(
                0x580 + node_id, "60", sdo_server, "12 01 00 00 00 00"
            ),  # acknowledge
            RxMsg(
                0x640, "40 00 12 00 00 00 00 00"
            ),  # cob_id 640h should now be ignored
            RxMsg(
                0x641, "40 00 12 00 00 00 00 00"
            ),  # cob_id 641h should now work (read number of subindex in object 0x1200)
            TxMsg(
                0x5D0, "4F 00 12 00 02 00 00 00"
            ),  # response with number of subindex (3)
        ]
    )

    assert n.sdo_servers[sdo_server].cob_rx == 0x641

    # change rx cob of sdo server and set to 0x642
    n.sdo_servers[sdo_server].cob_rx = 0x642

    adapter.test(
        [
            RxMsg(
                0x640, "40 00 12 00 00 00 00 00"
            ),  # cob_id 640h should now be ignored
            RxMsg(
                0x641, "40 00 12 00 00 00 00 00"
            ),  # cob_id 641h should now be ignored
            RxMsg(
                0x642, "40 00 12 00 00 00 00 00"
            ),  # cob_id 642h should work (read number of subindex in object 0x1200)
            TxMsg(
                0x5D0, "4F 00 12 00 02 00 00 00"
            ),  # response with number of subindex (3)
        ]
    )

    assert n.sdo_servers[sdo_server].cob_rx == 0x642

    # disable tx and rx cob of sdo server
    n.sdo_servers[sdo_server].cob_tx = None
    n.sdo_servers[sdo_server].cob_rx = None

    adapter.test(
        [
            RxMsg(
                0x642, "40 00 12 00 00 00 00 00"
            ),  # cob_id 642h should now be ignored
        ]
    )

    assert n.sdo_servers[sdo_server].cob_tx is None

    # sanity check to see if other sdo servers are affected
    assert n.sdo_servers[2].cob_rx is None
    assert n.sdo_servers[2].cob_tx is None
