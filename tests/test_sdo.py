from unittest.mock import Mock

import pytest

from durand import Node, Variable
from durand.datatypes import DatatypeEnum as DT
from durand.datatypes import struct_dict

from .adapter import MockAdapter


@pytest.mark.parametrize('node_id', [0x01, 0x7F])
def test_sdo_object_dictionary(node_id):
    n = Node(MockAdapter(), node_id)

    assert n.object_dictionary.lookup(0x1200, 0) == Variable(0x1200, 0, DT.UNSIGNED8, 'const', default=2)
    assert n.object_dictionary.lookup(0x1200, 1) == Variable(0x1200, 1, DT.UNSIGNED32, 'ro', default=0x600 + node_id)
    assert n.object_dictionary.lookup(0x1200, 2) == Variable(0x1200, 2, DT.UNSIGNED32, 'ro', default=0x580 + node_id)

    with pytest.raises(KeyError):
        n.object_dictionary.lookup(0x1201)  # other SDO server are not used in this configuration

@pytest.mark.parametrize('node_id', [0x01, 0x7F])
@pytest.mark.parametrize('index', [1, 2, 127])
def test_sdo_additional_servers(node_id, index):
    n = Node(MockAdapter(), node_id)
    n.add_sdo_server(index)

    assert n.object_dictionary.lookup(0x1200 + index, 0) == Variable(0x1200 + index, 0, DT.UNSIGNED8, 'const', default=3)
    assert n.object_dictionary.lookup(0x1200 + index, 1) == Variable(0x1200 + index, 1, DT.UNSIGNED32, 'rw', default=0x8000_0000)
    assert n.object_dictionary.lookup(0x1200 + index, 2) == Variable(0x1200 + index, 2, DT.UNSIGNED32, 'rw', default=0x8000_0000)
    assert n.object_dictionary.lookup(0x1200 + index, 3) == Variable(0x1200 + index, 3, DT.UNSIGNED8, 'rw')


@pytest.mark.parametrize('datatype', [DT.UNSIGNED8, DT.INTEGER8, DT.UNSIGNED16, DT.INTEGER16, DT.UNSIGNED32, DT.INTEGER32, DT.REAL32])
def test_sdo_expitited_download(datatype):
    adapter = MockAdapter()
    n = Node(adapter, 0x02)

    v = Variable(0x2000, 0, datatype, 'rw')
    n.object_dictionary.add_object(v)

    mock_write = Mock()
    n.object_dictionary.add_update_callback(v, mock_write)

    mock_write.assert_not_called()
    adapter.tx_mock.reset_mock()

    # with specified size
    size = struct_dict[datatype].size
    cmd = 0x23 + ((4 - size) << 2)
    adapter.receive(0x602, cmd.to_bytes(1, 'little') + b'\x00\x20\x00\x01\x02\x03\x04')

    adapter.tx_mock.assert_called_once_with(0x582, b'\x60\x00\x20\x00\x00\x00\x00\x00')
    value = struct_dict[datatype].unpack(b'\x01\x02\x03\x04'[:size])[0]
    mock_write.assert_called_once_with(value)

    # without specified size
    adapter.tx_mock.reset_mock()
    mock_write.reset_mock()

    adapter.receive(0x602, b'\x22\x00\x20\x00\x04\x03\x02\x01')
    adapter.tx_mock.assert_called_once_with(0x582, b'\x60\x00\x20\x00\x00\x00\x00\x00')

    value = struct_dict[datatype].unpack(b'\x04\x03\x02\x01'[:size])[0]
    mock_write.assert_called_once_with(value)
