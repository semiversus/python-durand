from unittest.mock import Mock, call
import struct
from binascii import crc_hqx

import pytest

from durand import Node, Variable
from durand.datatypes import DatatypeEnum as DT
from durand.datatypes import struct_dict
from durand.services.sdo.server import SDO_STRUCT
from durand.services.sdo import BaseDownloadHandler

from .adapter import MockAdapter


def build_sdo_packet(cs: int, index: int, subindex: int=0, data: bytes=b'', toggle: bool=False):
    cmd = (cs << 5) + (toggle << 4)

    if data:
        cmd += ((4 - len(data)) << 2) + 3  # set size and expetited

    return SDO_STRUCT.pack(cmd, index, subindex) + data + bytes(4 - len(data))


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


@pytest.mark.parametrize('datatype', [DT.UNSIGNED8, DT.INTEGER8, DT.UNSIGNED16, DT.INTEGER16, DT.UNSIGNED32, DT.INTEGER32, DT.REAL32, DT.DOMAIN])
def test_sdo_download_expetited(datatype):
    adapter = MockAdapter()
    n = Node(adapter, 0x02)

    v = Variable(0x2000, 0, datatype, 'rw')
    n.object_dictionary.add_object(v)

    mock_write = Mock()
    n.object_dictionary.update_callbacks[v].add(mock_write)

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


def test_sdo_download_fails():
    adapter = MockAdapter()
    n = Node(adapter, 0x02)

    # invalid client command specifier
    adapter.receive(0x602, build_sdo_packet(cs=7, index=0x1200, data=b'AB'))
    adapter.tx_mock.assert_called_with(0x582, b'\x80\x00\x12\x00\x01\x00\x04\x05')

    # write 'const' and 'ro' variables
    adapter.receive(0x602, build_sdo_packet(cs=1, index=0x1200, data=b'AB'))  # const entry
    adapter.tx_mock.assert_called_with(0x582, b'\x80\x00\x12\x00\x02\x00\x01\x06')

    adapter.receive(0x602, build_sdo_packet(cs=1, index=0x1200, subindex=1, data=b'AB'))  # ro entry
    adapter.tx_mock.assert_called_with(0x582, b'\x80\x00\x12\x01\x02\x00\x01\x06')

    # data size not matching
    var = Variable(0x2000, 0, DT.UNSIGNED8, 'rw', minimum=0x10, maximum=0x20)
    n.object_dictionary.add_object(var)
    adapter.receive(0x602, build_sdo_packet(cs=1, index=0x2000, data=b'AB'))  # write too many bytes to unsigned8
    adapter.tx_mock.assert_called_with(0x582, b'\x80\x00\x20\x00\x10\x00\x07\x06')

    # value to low or high
    adapter.receive(0x602, build_sdo_packet(cs=1, index=0x2000, data=b'\x0F'))  # write 15 (below minimum of 16)
    adapter.tx_mock.assert_called_with(0x582, b'\x80\x00\x20\x00\x32\x00\x09\x06')

    adapter.receive(0x602, build_sdo_packet(cs=1, index=0x2000, data=b'\x21'))  # write 33 (above maximum of 32)
    adapter.tx_mock.assert_called_with(0x582, b'\x80\x00\x20\x00\x31\x00\x09\x06')

    adapter.tx_mock.reset_mock()

    adapter.receive(0x602, build_sdo_packet(cs=1, index=0x2000, data=b'\x10'))  # write 16 (ok with minimum of 16)
    adapter.receive(0x602, build_sdo_packet(cs=1, index=0x2000, data=b'\x20'))  # write 32 (ok with maximum of 32)
    adapter.tx_mock.assert_has_calls([call(0x582, build_sdo_packet(3, 0x2000)), call(0x582, build_sdo_packet(3, 0x2000)) ])

    # write not working
    def fail(value):
        raise ValueError('Validation failed')

    n.object_dictionary.validate_callbacks[var].add(fail)
    adapter.receive(0x602, build_sdo_packet(cs=1, index=0x2000, data=b'\x10'))
    adapter.tx_mock.assert_called_with(0x582, b'\x80\x00\x20\x00\x20\x00\x00\x08')

    # object not existing
    adapter.receive(0x602, build_sdo_packet(cs=1, index=0x2001, data=b'\x10'))  # write non existing object
    adapter.tx_mock.assert_called_with(0x582, b'\x80\x01\x20\x00\x00\x00\x02\x06')

    # subindex not existing
    adapter.receive(0x602, build_sdo_packet(cs=1, index=0x2000, subindex= 1, data=b'\x10'))  # write non existing object
    adapter.tx_mock.assert_called_with(0x582, b'\x80\x00\x20\x01\x11\x00\x09\x06')


@pytest.mark.parametrize('datatype', [DT.VISIBLE_STRING, DT.DOMAIN, DT.OCTET_STRING])
def test_sdo_download_segmented(datatype):
    adapter = MockAdapter()
    n = Node(adapter, 0x02)

    var = Variable(0x2000, 0, datatype, 'rw')
    n.object_dictionary.add_object(var)

    adapter.receive(0x602, build_sdo_packet(cs=1, index=0x2000, subindex=0))
    adapter.tx_mock.assert_called_with(0x582, b'\x60\x00\x20\x00\x00\x00\x00\x00')

    adapter.receive(0x602, b'\x00ABCDEFG')
    adapter.tx_mock.assert_called_with(0x582, b'\x20\x00\x00\x00\x00\x00\x00\x00')

    adapter.receive(0x602, b'\x1AHI')
    adapter.tx_mock.assert_called_with(0x582, b'\x30\x00\x00\x00\x00\x00\x00\x00')

    assert n.object_dictionary.read(var) == 0

    adapter.receive(0x602, b'\x07JKLM')
    adapter.tx_mock.assert_called_with(0x582, b'\x20\x00\x00\x00\x00\x00\x00\x00')

    assert n.object_dictionary.read(var) == b'ABCDEFGHIJKLM'


@pytest.mark.parametrize('datatype', [DT.UNSIGNED8, DT.INTEGER8, DT.UNSIGNED16, DT.INTEGER16, DT.UNSIGNED32, DT.INTEGER32, DT.REAL32])
def test_sdo_download_segmented_numeric(datatype):
    adapter = MockAdapter()
    n = Node(adapter, 0x02)

    v = Variable(0x2000, 0, datatype, 'rw')
    n.object_dictionary.add_object(v)

    mock_write = Mock()
    n.object_dictionary.update_callbacks[v].add(mock_write)

    mock_write.assert_not_called()
    adapter.tx_mock.reset_mock()

    # with specified size
    size = struct_dict[datatype].size
    adapter.receive(0x602, b'\x21\x00\x20\x00' + struct.pack('<I', size))
    adapter.tx_mock.assert_called_once_with(0x582, b'\x60\x00\x20\x00\x00\x00\x00\x00')

    value = struct_dict[datatype].unpack(b'\x01\x02\x03\x04'[:size])[0]

    for index in range(size):
        cmd = 0x0C + ((index % 2) << 4) + (index == size - 1)
        adapter.receive(0x602, cmd.to_bytes(1, 'little') + b'\x01\x02\x03\x04'[index:index + 1] + bytes(6))

        response = 0x20 + ((index % 2) << 4)
        adapter.tx_mock.assert_called_with(0x582, response.to_bytes(1, 'little') + bytes(7))

    mock_write.assert_called_once_with(value)

    # without specified size
    adapter.tx_mock.reset_mock()
    mock_write.reset_mock()

    adapter.receive(0x602, b'\x20\x00\x20\x00\x00\x00\x00\x00')
    adapter.tx_mock.assert_called_once_with(0x582, b'\x60\x00\x20\x00\x00\x00\x00\x00')

    value = struct_dict[datatype].unpack(b'\x04\x03\x02\x01'[:size])[0]

    for index in range(size):
        cmd = 0x0C + ((index % 2) << 4) + (index == size - 1)
        adapter.receive(0x602, cmd.to_bytes(1, 'little') + b'\x04\x03\x02\x01'[index:index + 1] + bytes(6))

        response = 0x20 + ((index % 2) << 4)
        adapter.tx_mock.assert_called_with(0x582, response.to_bytes(1, 'little') + bytes(7))

    mock_write.assert_called_once_with(value)


def test_sdo_download_segmented_fails():
    adapter = MockAdapter()
    n = Node(adapter, 0x02)

    # write 'const' and 'ro' variables
    adapter.receive(0x602, build_sdo_packet(cs=1, index=0x1200))  # const entry
    adapter.tx_mock.assert_called_with(0x582, b'\x80\x00\x12\x00\x02\x00\x01\x06')

    adapter.receive(0x602, build_sdo_packet(cs=1, index=0x1200, subindex=1))  # ro entry
    adapter.tx_mock.assert_called_with(0x582, b'\x80\x00\x12\x01\x02\x00\x01\x06')

    # data size not matching
    var1 = Variable(0x2000, 0, DT.UNSIGNED8, 'rw', minimum=0x10, maximum=0x20)
    n.object_dictionary.add_object(var1)

    adapter.receive(0x602, build_sdo_packet(cs=1, index=0x2000))
    adapter.receive(0x602, b'\x01' + bytes(7))  # write too many bytes to unsigned8
    adapter.tx_mock.assert_called_with(0x582, b'\x80\x00\x20\x00\x10\x00\x07\x06')

    # value to low or high
    adapter.receive(0x602, build_sdo_packet(cs=1, index=0x2000))
    adapter.receive(0x602, b'\x0D\x0E' + bytes(6))  # write 15 (below minimum of 16)
    adapter.tx_mock.assert_called_with(0x582, b'\x80\x00\x20\x00\x32\x00\x09\x06')

    adapter.receive(0x602, build_sdo_packet(cs=1, index=0x2000))
    adapter.receive(0x602, b'\x0D\x21' + bytes(6))  # write 33 (above maximum of 32)
    adapter.tx_mock.assert_called_with(0x582, b'\x80\x00\x20\x00\x31\x00\x09\x06')

    adapter.tx_mock.reset_mock()

    adapter.receive(0x602, build_sdo_packet(cs=1, index=0x2000))
    adapter.receive(0x602, b'\x0D\x10' + bytes(6))  # write 16 (ok with minimum of 16)

    adapter.receive(0x602, build_sdo_packet(cs=1, index=0x2000))
    adapter.receive(0x602, b'\x0D\x20' + bytes(6))  # write 32 (ok with maximum of 32)

    adapter.tx_mock.assert_has_calls([call(0x582, build_sdo_packet(3, 0x2000)), call(0x582, b'\x20' + bytes(7)),
                                      call(0x582, build_sdo_packet(3, 0x2000)), call(0x582, b'\x20' + bytes(7)) ])

    # download segment without init
    adapter.receive(0x602, b'\x0D\x10' + bytes(6))  # write 16
    adapter.tx_mock.assert_called_with(0x582, b'\x80\x00\x00\x00\x01\x00\x04\x05')

    # wrong toggle bit (initial)
    adapter.receive(0x602, build_sdo_packet(cs=1, index=0x2000))
    adapter.receive(0x602, b'\x1D\x10' + bytes(6))  # write 16 with toggle bit set
    adapter.tx_mock.assert_called_with(0x582, b'\x80\x00\x20\x00\x00\x00\x03\x05')

    # write not working
    var2 = Variable(0x2001, 0, DT.UNSIGNED8, 'rw')
    n.object_dictionary.add_object(var2)

    def fail(value):
        raise ValueError('Validation failed')

    n.object_dictionary.validate_callbacks[var2].add(fail)
    adapter.receive(0x602, build_sdo_packet(cs=1, index=0x2001))
    adapter.receive(0x602, b'\x0D\x10' + bytes(6))  # write 16
    adapter.tx_mock.assert_called_with(0x582, b'\x80\x01\x20\x00\x20\x00\x00\x08')

    # abort
    adapter.tx_mock.reset_mock()

    adapter.receive(0x602, build_sdo_packet(cs=1, index=0x2000))
    adapter.receive(0x602, b'\x80\x00\x20\x00\x01\x02\x03\x04')
    adapter.receive(0x602, b'\x0D\x12' + bytes(6))  # write 18

    adapter.tx_mock.assert_has_calls([call(0x582, build_sdo_packet(3, 0x2000)), call(0x582, b'\x80\x00\x00\x00\x01\x00\x04\x05')])
    assert n.object_dictionary.read(var1) == 32

    # abort another transfer
    adapter.tx_mock.reset_mock()

    adapter.receive(0x602, build_sdo_packet(cs=1, index=0x2000))
    adapter.receive(0x602, b'\x80\x00\x20\x01\x01\x02\x03\x04')
    adapter.receive(0x602, b'\x0D\x11' + bytes(6))  # write 17

    adapter.tx_mock.assert_has_calls([call(0x582, build_sdo_packet(3, 0x2000)), call(0x582, b'\x20' + bytes(7))])
    assert n.object_dictionary.read(var1) == 17


def test_sdo_download_handler():
    adapter = MockAdapter()
    n = Node(adapter, 0x02)

    var1 = Variable(0x2000, 0, DT.DOMAIN, 'rw')
    var2 = Variable(0x2001, 0, DT.DOMAIN, 'rw')

    n.object_dictionary.add_object(var1)
    n.object_dictionary.add_object(var2)

    handler_mock = Mock()

    def download_callback(node: None, variable: Variable, size: int):
        if variable.index == 0x2001:
            return handler_mock

    n.sdo_servers[0].download_manager.set_handler_callback(download_callback)

    # test without Downloadhandler
    adapter.receive(0x602, build_sdo_packet(cs=1, index=0x2000))
    adapter.receive(0x602, b'\x0D\x10' + bytes(6))

    assert n.object_dictionary.read(var1) == b'\x10'

    handler_mock.assert_not_called()

    # test wit Downloadhandler
    adapter.receive(0x602, build_sdo_packet(cs=1, index=0x2001))
    adapter.receive(0x602, b'\x0D\x11' + bytes(6))

    assert n.object_dictionary.read(var2) == 0
    handler_mock.on_receive.assert_called_once_with(b'\x11')
    handler_mock.on_finish.assert_called_once_with()
    handler_mock.on_abort.assert_not_called()

    # aborting Downloadhandler
    handler_mock.assert_not_called()

    adapter.receive(0x602, build_sdo_packet(cs=1, index=0x2001))
    adapter.receive(0x602, b'\x1D\x11' + bytes(6))

    assert n.object_dictionary.read(var2) == 0
    handler_mock.on_receive.assert_not_called()
    handler_mock.on_finish.assert_not_called()
    handler_mock.on_abort.assert_called_once_with()


@pytest.mark.parametrize('size', [1, 7, 8, 889, 890, 889 * 2, 889 * 2 + 1, 4096, 100_000])
@pytest.mark.parametrize('crc', [True, False])
def test_sdo_download_block(size, crc):
    adapter = MockAdapter()
    n = Node(adapter, 0x02)

    var = Variable(0x2000, 0, DT.DOMAIN, 'rw')
    n.object_dictionary.add_object(var)

    adapter.tx_mock.reset_mock()

    cmd = 0xC0 + (crc << 2)
    adapter.receive(0x602, cmd.to_bytes(1, 'little') + b'\x00\x20\x00\x00\x00\x00\x00')
    adapter.tx_mock.assert_called_once_with(0x582, b'\xA4\x00\x20\x00\x7F\x00\x00\x00')

    for _ in range((size - 1) // 889):
        adapter.tx_mock.reset_mock()

        for sub_block_index in range(1, 128):
            adapter.tx_mock.assert_not_called()
            adapter.receive(0x602, sub_block_index.to_bytes(1, 'little') + b'\xAA' * 7)

        adapter.tx_mock.assert_called_once_with(0x582, b'\xA2\x7F\x7F\x00\x00\x00\x00\x00')

    adapter.tx_mock.reset_mock()

    for sub_block_index in range(1, ((size - 1) % 889) // 7 + 1 if size else 0):
        adapter.tx_mock.assert_not_called()
        adapter.receive(0x602, sub_block_index.to_bytes(1, 'little') + b'\xAA' * 7)

    adapter.tx_mock.reset_mock()

    if size != 0:
        segment_nr = ((size - 1) % 889) // 7 + 1
        cmd = 0x80 + segment_nr
        adapter.receive(0x602, cmd.to_bytes(1, 'little') + b'\xAA' * ((size - 1) % 7 + 1) + bytes(6 - (size - 1) % 7))

        adapter.tx_mock.assert_called_once_with(0x582, b'\xA2' + segment_nr.to_bytes(1, 'little') + b'\x7F\x00\x00\x00\x00\x00')

    cmd = 0xC1 + ((6 - (size - 1) % 7) << 2)

    if crc and size:
        crc_bytes = struct.pack('<H', crc_hqx(b'\xAA' * size, 0))
    else:
        crc_bytes = bytes(2)

    adapter.tx_mock.reset_mock()
    adapter.receive(0x602, cmd.to_bytes(1, 'little') + crc_bytes + bytes(5))
    adapter.tx_mock.assert_called_once_with(0x582, b'\xA1' + bytes(7))

    assert n.object_dictionary.read(var) == b'\xAA' * size


@pytest.mark.parametrize('datatype', [DT.UNSIGNED8, DT.INTEGER8, DT.UNSIGNED16, DT.INTEGER16, DT.UNSIGNED32, DT.INTEGER32, DT.REAL32, DT.DOMAIN])
def test_sdo_upload_expetited(datatype):
    adapter = MockAdapter()
    n = Node(adapter, 0x02)

    value = struct_dict[datatype].unpack(b'\x01\x02\x03\x04'[:struct_dict[datatype].size])[0]

    v = Variable(0x2000, 0, datatype, 'rw', default=value)
    n.object_dictionary.add_object(v)

    mock_write = Mock()
    n.object_dictionary.update_callbacks[v].add(mock_write)

    mock_write.assert_not_called()
    adapter.tx_mock.reset_mock()

    # with specified size
    size = struct_dict[datatype].size
    adapter.receive(0x602, b'\x40\x00\x20\x00\x00\x00\x00\x00')

    cmd = 0x43 + ((4 - size) << 2)
    adapter.tx_mock.assert_called_once_with(0x582, cmd.to_bytes(1, 'little') + b'\x00\x20\x00' + b'\x01\x02\x03\x04'[:size] + bytes(4 - size))

def test_sdo_upload_fails():
    adapter = MockAdapter()
    n = Node(adapter, 0x02)

    # read 'wo' variables
    v = Variable(0x2000, 0, DT.INTEGER8, 'wo', default=0)
    n.object_dictionary.add_object(v)

    adapter.receive(0x602, build_sdo_packet(cs=2, index=0x2000))  # wo entry
    adapter.tx_mock.assert_called_with(0x582, b'\x80\x00\x20\x00\x01\x00\x01\x06')

    # read not working
    v = Variable(0x2001, 0, DT.INTEGER8, 'rw', default=0)
    n.object_dictionary.add_object(v)

    def fail(value):
        raise ValueError('Validation failed')

    n.object_dictionary.set_read_callback(v, fail)
    adapter.receive(0x602, build_sdo_packet(cs=2, index=0x2001))
    adapter.tx_mock.assert_called_with(0x582, b'\x80\x01\x20\x00\x00\x00\x06\x06')
