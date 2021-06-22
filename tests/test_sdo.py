import pytest

from durand import Node, Variable
from durand import datatypes as DT

@pytest.mark.parametrize('node_id', [0x01, 0x7F])
def test_sdo_object_dictionary(node_id):
    n = Node(None, 0x01)

    assert n.object_dictionary.lookup(0x1200, 0) == Variable(0x1200, 0, DT.UNSIGNED8, 'ro', default=2)
    assert n.object_dictionary.lookup(0x1200, 1) == Variable(0x1200, 0, DT.UNSIGNED8, 'rw', default=0x600 + node_id)
    assert n.object_dictionary.lookup(0x1200, 2) == Variable(0x1200, 0, DT.UNSIGNED8, 'rw', default=0x580 + node_id)



