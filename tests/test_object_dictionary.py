""" Testing object dictionary functionality """
import re

import pytest

from durand import Node, Variable
from durand.datatypes import DatatypeEnum as DT

from .mock_network import MockNetwork


def test_write():
    # create the node
    network = MockNetwork()
    node = Node(network, node_id=2)

    # add a variable with index 0x2000:0 to the object dictionary of the node
    node.object_dictionary[0x2000] = Variable(DT.INTEGER16, "rw", value=5)
    assert node.object_dictionary.read(0x2000, 0) == 5

    # these test should pass
    node.object_dictionary.write(0x2000, 0, 32767)
    assert node.object_dictionary.read(0x2000, 0) == 32767

    node.object_dictionary.write(0x2000, 0, -32768)
    assert node.object_dictionary.read(0x2000, 0) == -32768
    
    # test too low value
    with pytest.raises(ValueError, match=re.escape('Value -32769 is too low (minimum is -32768)')):
        node.object_dictionary.write(0x2000, 0, value=-32769)

    # test too high value
    with pytest.raises(ValueError, match=re.escape('Value 32768 is too high (minimum is 32767)')):
        node.object_dictionary.write(0x2000, 0, value=32768)


def test_access_of_unknown_variable():
    # create the node
    network = MockNetwork()
    node = Node(network, node_id=2)

    with pytest.raises(KeyError):
        node.object_dictionary.write(0x2000, 0, 5)
    
    with pytest.raises(KeyError):
        node.object_dictionary.read(0x2000, 0)