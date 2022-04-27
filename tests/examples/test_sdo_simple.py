from durand import Node, Variable
from durand.datatypes import DatatypeEnum as DT

from ..adapter import MockAdapter, TxMsg, RxMsg


def test_simple_access():
    adapter = MockAdapter()

    # create the node
    node = Node(adapter, node_id=2)

    # add a variable with index 0x2000:0 to the object dictionary of the node
    node.object_dictionary.add_object(
        Variable(0x2000, 0, DT.INTEGER16, 'rw', default=5)
    )

    # upload the value 1 via SDO
    adapter.test([
        RxMsg(0x602, '2b 00 20 00 01 00 00 00'),  # send the request
        TxMsg(0x582, '60 00 20 00 00 00 00 00'),  # receive the acknowledge
    ])

    # download object via SDO
    adapter.test([
        RxMsg(0x602, '40 00 20 00 00 00 00 00'),
        TxMsg(0x582, '4b 00 20 00 01 00 00 00'),
    ])

    