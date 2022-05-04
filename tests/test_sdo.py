from unittest.mock import Mock, call
import struct
from binascii import crc_hqx

import pytest

from durand import Node, Variable, Record
from durand.datatypes import DatatypeEnum as DT
from durand.datatypes import struct_dict
from durand.services.sdo.server import SDO_STRUCT
from durand.services.sdo import BaseUploadHandler
from durand.services.nmt import StateEnum

from .adapter import MockAdapter


def build_sdo_packet(
    cs: int, index: int, subindex: int = 0, data: bytes = b"", toggle: bool = False
):
    cmd = (cs << 5) + (toggle << 4)

    if data:
        cmd += ((4 - len(data)) << 2) + 3  # set size and expetited

    return SDO_STRUCT.pack(cmd, index, subindex) + data + bytes(4 - len(data))


@pytest.mark.parametrize(
    "datatype",
    [
        DT.UNSIGNED8,
        DT.INTEGER8,
        DT.UNSIGNED16,
        DT.INTEGER16,
        DT.UNSIGNED32,
        DT.INTEGER32,
        DT.REAL32,
    ],
)
@pytest.mark.parametrize("with_handler", [True, False])
def test_sdo_download_expetited(datatype, with_handler):
    adapter = MockAdapter()
    n = Node(adapter, 0x02)

    handler_mock = Mock()
    handler_calls = list()

    v = Variable(datatype, "rw")
    n.object_dictionary[0x2000] = v

    def download_handler(node, index, subindex, size):
        assert node == n
        assert index == 0x2000
        assert subindex == 0
        return handler_mock

    if with_handler:
        n.sdo_servers[0].download_manager.set_handler_callback(download_handler)

    mock_write = Mock()
    n.object_dictionary.update_callbacks[(0x2000, 0)].add(mock_write)

    mock_write.assert_not_called()
    adapter.tx_mock.reset_mock()

    # with specified size
    size = struct_dict[datatype].size
    cmd = 0x23 + ((4 - size) << 2)
    adapter.receive(0x602, cmd.to_bytes(1, "little") + b"\x00\x20\x00\x01\x02\x03\x04")

    handler_calls.append(call.on_receive(b"\x01\x02\x03\x04"[:size]))
    handler_calls.append(call.on_finish())

    adapter.tx_mock.assert_called_once_with(0x582, b"\x60\x00\x20\x00\x00\x00\x00\x00")
    value = struct_dict[datatype].unpack(b"\x01\x02\x03\x04"[:size])[0]

    if with_handler:
        mock_write.assert_not_called()
        assert handler_mock.mock_calls == handler_calls
    else:
        mock_write.assert_called_once_with(value)
        assert not handler_mock.mock_calls

    # without specified size
    adapter.tx_mock.reset_mock()
    mock_write.reset_mock()
    handler_mock.reset_mock()

    adapter.receive(0x602, b"\x22\x00\x20\x00\x04\x03\x02\x01")
    adapter.tx_mock.assert_called_once_with(0x582, b"\x60\x00\x20\x00\x00\x00\x00\x00")

    handler_calls = [call.on_receive(b"\x04\x03\x02\x01"[:size]), call.on_finish()]

    value = struct_dict[datatype].unpack(b"\x04\x03\x02\x01"[:size])[0]

    if with_handler:
        mock_write.assert_not_called()
        assert handler_mock.mock_calls == handler_calls
    else:
        mock_write.assert_called_once_with(value)
        assert not handler_mock.mock_calls


def test_sdo_download_fails():
    adapter = MockAdapter()
    n = Node(adapter, 0x02)

    # invalid client command specifier
    adapter.receive(0x602, build_sdo_packet(cs=7, index=0x1200, data=b"AB"))
    adapter.tx_mock.assert_called_with(0x582, b"\x80\x00\x12\x00\x01\x00\x04\x05")

    # write 'const' and 'ro' variables
    adapter.receive(
        0x602, build_sdo_packet(cs=1, index=0x1200, data=b"AB")
    )  # const entry
    adapter.tx_mock.assert_called_with(0x582, b"\x80\x00\x12\x00\x02\x00\x01\x06")

    adapter.receive(
        0x602, build_sdo_packet(cs=1, index=0x1200, subindex=1, data=b"AB")
    )  # ro entry
    adapter.tx_mock.assert_called_with(0x582, b"\x80\x00\x12\x01\x02\x00\x01\x06")

    # data size not matching
    var = Variable(DT.UNSIGNED8, "rw", minimum=0x10, maximum=0x20)
    n.object_dictionary[0x2000] = var

    adapter.receive(
        0x602, build_sdo_packet(cs=1, index=0x2000, data=b"AB")
    )  # write too many bytes to unsigned8
    adapter.tx_mock.assert_called_with(0x582, b"\x80\x00\x20\x00\x10\x00\x07\x06")

    # value to low or high
    adapter.receive(
        0x602, build_sdo_packet(cs=1, index=0x2000, data=b"\x0F")
    )  # write 15 (below minimum of 16)
    adapter.tx_mock.assert_called_with(0x582, b"\x80\x00\x20\x00\x32\x00\x09\x06")

    adapter.receive(
        0x602, build_sdo_packet(cs=1, index=0x2000, data=b"\x21")
    )  # write 33 (above maximum of 32)
    adapter.tx_mock.assert_called_with(0x582, b"\x80\x00\x20\x00\x31\x00\x09\x06")

    adapter.tx_mock.reset_mock()

    adapter.receive(
        0x602, build_sdo_packet(cs=1, index=0x2000, data=b"\x10")
    )  # write 16 (ok with minimum of 16)
    adapter.receive(
        0x602, build_sdo_packet(cs=1, index=0x2000, data=b"\x20")
    )  # write 32 (ok with maximum of 32)
    adapter.tx_mock.assert_has_calls(
        [
            call(0x582, build_sdo_packet(3, 0x2000)),
            call(0x582, build_sdo_packet(3, 0x2000)),
        ]
    )

    # write not working
    def fail(value):
        raise ValueError("Validation failed")

    n.object_dictionary.validate_callbacks[(0x2000, 0)].add(fail)
    adapter.receive(0x602, build_sdo_packet(cs=1, index=0x2000, data=b"\x10"))
    adapter.tx_mock.assert_called_with(0x582, b"\x80\x00\x20\x00\x20\x00\x00\x08")

    # object not existing
    adapter.receive(
        0x602, build_sdo_packet(cs=1, index=0x2001, data=b"\x10")
    )  # write non existing object
    adapter.tx_mock.assert_called_with(0x582, b"\x80\x01\x20\x00\x00\x00\x02\x06")

    # subindex not existing
    record = Record()
    record[0] = Variable(DT.UNSIGNED8, "rw")
    n.object_dictionary[0x2002] = record

    adapter.receive(
        0x602, build_sdo_packet(cs=1, index=0x2002, subindex=1, data=b"\x10")
    )  # write non existing object
    adapter.tx_mock.assert_called_with(0x582, b"\x80\x02\x20\x01\x11\x00\x09\x06")


@pytest.mark.parametrize("datatype", [DT.VISIBLE_STRING, DT.DOMAIN, DT.OCTET_STRING])
def test_sdo_download_segmented(datatype):
    adapter = MockAdapter()
    n = Node(adapter, 0x02)

    var = Variable(datatype, "rw")
    n.object_dictionary[0x2000] = var

    adapter.receive(0x602, build_sdo_packet(cs=1, index=0x2000, subindex=0))
    adapter.tx_mock.assert_called_with(0x582, b"\x60\x00\x20\x00\x00\x00\x00\x00")

    adapter.receive(0x602, b"\x00ABCDEFG")
    adapter.tx_mock.assert_called_with(0x582, b"\x20\x00\x00\x00\x00\x00\x00\x00")

    adapter.receive(0x602, b"\x1AHI")
    adapter.tx_mock.assert_called_with(0x582, b"\x30\x00\x00\x00\x00\x00\x00\x00")

    assert n.object_dictionary.read(0x2000, 0) == b""

    adapter.receive(0x602, b"\x07JKLM")
    adapter.tx_mock.assert_called_with(0x582, b"\x20\x00\x00\x00\x00\x00\x00\x00")

    assert n.object_dictionary.read(0x2000, 0) == b"ABCDEFGHIJKLM"


@pytest.mark.parametrize(
    "datatype",
    [
        DT.UNSIGNED8,
        DT.INTEGER8,
        DT.UNSIGNED16,
        DT.INTEGER16,
        DT.UNSIGNED32,
        DT.INTEGER32,
        DT.REAL32,
    ],
)
def test_sdo_download_segmented_numeric(datatype):
    adapter = MockAdapter()
    n = Node(adapter, 0x02)

    v = Variable(datatype, "rw")
    n.object_dictionary[0x2000] = v

    mock_write = Mock()
    n.object_dictionary.update_callbacks[(0x2000, 0)].add(mock_write)

    mock_write.assert_not_called()
    adapter.tx_mock.reset_mock()

    # with specified size
    size = struct_dict[datatype].size
    adapter.receive(0x602, b"\x21\x00\x20\x00" + struct.pack("<I", size))
    adapter.tx_mock.assert_called_once_with(0x582, b"\x60\x00\x20\x00\x00\x00\x00\x00")

    value = struct_dict[datatype].unpack(b"\x01\x02\x03\x04"[:size])[0]

    for index in range(size):
        cmd = 0x0C + ((index % 2) << 4) + (index == size - 1)
        adapter.receive(
            0x602,
            cmd.to_bytes(1, "little")
            + b"\x01\x02\x03\x04"[index : index + 1]
            + bytes(6),
        )

        response = 0x20 + ((index % 2) << 4)
        adapter.tx_mock.assert_called_with(
            0x582, response.to_bytes(1, "little") + bytes(7)
        )

    mock_write.assert_called_once_with(value)

    # without specified size
    adapter.tx_mock.reset_mock()
    mock_write.reset_mock()

    adapter.receive(0x602, b"\x20\x00\x20\x00\x00\x00\x00\x00")
    adapter.tx_mock.assert_called_once_with(0x582, b"\x60\x00\x20\x00\x00\x00\x00\x00")

    value = struct_dict[datatype].unpack(b"\x04\x03\x02\x01"[:size])[0]

    for index in range(size):
        cmd = 0x0C + ((index % 2) << 4) + (index == size - 1)
        adapter.receive(
            0x602,
            cmd.to_bytes(1, "little")
            + b"\x04\x03\x02\x01"[index : index + 1]
            + bytes(6),
        )

        response = 0x20 + ((index % 2) << 4)
        adapter.tx_mock.assert_called_with(
            0x582, response.to_bytes(1, "little") + bytes(7)
        )

    mock_write.assert_called_once_with(value)


def test_sdo_download_segmented_fails():
    adapter = MockAdapter()
    n = Node(adapter, 0x02)

    # write 'const' and 'ro' variables
    adapter.receive(0x602, build_sdo_packet(cs=1, index=0x1200))  # const entry
    adapter.tx_mock.assert_called_with(0x582, b"\x80\x00\x12\x00\x02\x00\x01\x06")

    adapter.receive(0x602, build_sdo_packet(cs=1, index=0x1200, subindex=1))  # ro entry
    adapter.tx_mock.assert_called_with(0x582, b"\x80\x00\x12\x01\x02\x00\x01\x06")

    # data size not matching
    var1 = Variable(DT.UNSIGNED8, "rw", minimum=0x10, maximum=0x20)
    n.object_dictionary[0x2000] = var1

    adapter.receive(0x602, build_sdo_packet(cs=1, index=0x2000))
    adapter.receive(0x602, b"\x01" + bytes(7))  # write too many bytes to unsigned8
    adapter.tx_mock.assert_called_with(0x582, b"\x80\x00\x20\x00\x10\x00\x07\x06")

    # value to low or high
    adapter.receive(0x602, build_sdo_packet(cs=1, index=0x2000))
    adapter.receive(0x602, b"\x0D\x0E" + bytes(6))  # write 15 (below minimum of 16)
    adapter.tx_mock.assert_called_with(0x582, b"\x80\x00\x20\x00\x32\x00\x09\x06")

    adapter.receive(0x602, build_sdo_packet(cs=1, index=0x2000))
    adapter.receive(0x602, b"\x0D\x21" + bytes(6))  # write 33 (above maximum of 32)
    adapter.tx_mock.assert_called_with(0x582, b"\x80\x00\x20\x00\x31\x00\x09\x06")

    adapter.tx_mock.reset_mock()

    adapter.receive(0x602, build_sdo_packet(cs=1, index=0x2000))
    adapter.receive(0x602, b"\x0D\x10" + bytes(6))  # write 16 (ok with minimum of 16)

    adapter.receive(0x602, build_sdo_packet(cs=1, index=0x2000))
    adapter.receive(0x602, b"\x0D\x20" + bytes(6))  # write 32 (ok with maximum of 32)

    adapter.tx_mock.assert_has_calls(
        [
            call(0x582, build_sdo_packet(3, 0x2000)),
            call(0x582, b"\x20" + bytes(7)),
            call(0x582, build_sdo_packet(3, 0x2000)),
            call(0x582, b"\x20" + bytes(7)),
        ]
    )

    # download segment without init
    adapter.receive(0x602, b"\x0D\x10" + bytes(6))  # write 16
    adapter.tx_mock.assert_called_with(0x582, b"\x80\x00\x00\x00\x01\x00\x04\x05")

    # wrong toggle bit (initial)
    adapter.receive(0x602, build_sdo_packet(cs=1, index=0x2000))
    adapter.receive(0x602, b"\x1D\x10" + bytes(6))  # write 16 with toggle bit set
    adapter.tx_mock.assert_called_with(0x582, b"\x80\x00\x20\x00\x00\x00\x03\x05")

    # write not working
    var2 = Variable(DT.UNSIGNED8, "rw")
    n.object_dictionary[0x2001] = var2

    def fail(value):
        raise ValueError("Validation failed")

    n.object_dictionary.validate_callbacks[(0x2001, 0)].add(fail)
    adapter.receive(0x602, build_sdo_packet(cs=1, index=0x2001))
    adapter.receive(0x602, b"\x0D\x10" + bytes(6))  # write 16
    adapter.tx_mock.assert_called_with(0x582, b"\x80\x01\x20\x00\x20\x00\x00\x08")

    # abort
    adapter.tx_mock.reset_mock()

    adapter.receive(0x602, build_sdo_packet(cs=1, index=0x2000))
    adapter.receive(0x602, b"\x80\x00\x20\x00\x01\x02\x03\x04")
    adapter.receive(0x602, b"\x0D\x12" + bytes(6))  # write 18

    adapter.tx_mock.assert_has_calls(
        [
            call(0x582, build_sdo_packet(3, 0x2000)),
            call(0x582, b"\x80\x00\x00\x00\x01\x00\x04\x05"),
        ]
    )
    assert n.object_dictionary.read(0x2000, 0) == 32

    # abort another transfer
    adapter.tx_mock.reset_mock()

    adapter.receive(0x602, build_sdo_packet(cs=1, index=0x2000))
    adapter.receive(0x602, b"\x80\x00\x20\x01\x01\x02\x03\x04")
    adapter.receive(0x602, b"\x0D\x11" + bytes(6))  # write 17

    adapter.tx_mock.assert_has_calls(
        [call(0x582, build_sdo_packet(3, 0x2000)), call(0x582, b"\x20" + bytes(7))]
    )
    assert n.object_dictionary.read(0x2000, 0) == 17


def test_sdo_download_segmented_handler():
    adapter = MockAdapter()
    n = Node(adapter, 0x02)

    var1 = Variable(DT.DOMAIN, "rw")
    var2 = Variable(DT.DOMAIN, "rw")

    n.object_dictionary[0x2000] = var1
    n.object_dictionary[0x2001] = var2

    handler_mock = Mock()

    def download_callback(node: None, index: int, subindex: int, size: int):
        if index == 0x2001:
            return handler_mock

    n.sdo_servers[0].download_manager.set_handler_callback(download_callback)

    # test without Downloadhandler
    adapter.receive(0x602, build_sdo_packet(cs=1, index=0x2000))
    adapter.receive(0x602, b"\x0D\x10" + bytes(6))

    assert n.object_dictionary.read(0x2000, 0) == b"\x10"

    handler_mock.assert_not_called()

    # test wit Downloadhandler
    adapter.receive(0x602, build_sdo_packet(cs=1, index=0x2001))
    adapter.receive(0x602, b"\x0D\x11" + bytes(6))

    assert n.object_dictionary.read(0x2001, 0) == b""
    handler_mock.on_receive.assert_called_once_with(b"\x11")
    handler_mock.on_finish.assert_called_once_with()
    handler_mock.on_abort.assert_not_called()

    # aborting Downloadhandler
    handler_mock.reset_mock()

    adapter.receive(0x602, build_sdo_packet(cs=1, index=0x2001))
    adapter.receive(0x602, b"\x80\x01\x20\x00\x01\x02\x03\x04")
    adapter.receive(0x602, b"\x1D\x11" + bytes(6))
    adapter.receive(0x602, b"\x80\x01\x20\x00\x01\x02\x03\x04")

    assert n.object_dictionary.read(0x2001, 0) == b""
    handler_mock.on_receive.assert_not_called()
    handler_mock.on_finish.assert_not_called()
    handler_mock.on_abort.assert_called_once_with()


@pytest.mark.parametrize(
    "size", [1, 7, 8, 889, 890, 889 * 2, 889 * 2 + 1, 4096, 10_000]
)
@pytest.mark.parametrize("crc", [True, False])
@pytest.mark.parametrize("with_handler", [True, False])
@pytest.mark.parametrize("with_size", [True, False])
def test_sdo_download_block(size, crc, with_handler, with_size):
    adapter = MockAdapter()
    n = Node(adapter, 0x02)

    var = Variable(DT.DOMAIN, "rw")
    n.object_dictionary[0x2000] = var

    handler_mock = Mock()
    handler_calls = list()

    def download_handler(node, index, subindex, size):
        assert node == n
        assert index == 0x2000
        assert subindex == 0
        return handler_mock

    if with_handler:
        n.sdo_servers[0].download_manager.set_handler_callback(download_handler)

    adapter.tx_mock.reset_mock()

    cmd = 0xC0 + (crc << 2) + (with_size << 1)
    size_bytes = struct.pack("<I", size) if with_size else bytes(4)

    adapter.receive(0x602, cmd.to_bytes(1, "little") + b"\x00\x20\x00" + size_bytes)
    adapter.tx_mock.assert_called_once_with(0x582, b"\xA4\x00\x20\x00\x7F\x00\x00\x00")

    for _ in range((size - 1) // 889):
        adapter.tx_mock.reset_mock()

        for sub_block_index in range(1, 128):
            adapter.tx_mock.assert_not_called()
            adapter.receive(0x602, sub_block_index.to_bytes(1, "little") + b"\xAA" * 7)
            handler_calls.append(call.on_receive(b"\xaa" * 7))

        adapter.tx_mock.assert_called_once_with(
            0x582, b"\xA2\x7F\x7F\x00\x00\x00\x00\x00"
        )

    adapter.tx_mock.reset_mock()

    for sub_block_index in range(1, ((size - 1) % 889) // 7 + 1 if size else 0):
        adapter.tx_mock.assert_not_called()
        adapter.receive(0x602, sub_block_index.to_bytes(1, "little") + b"\xAA" * 7)
        handler_calls.append(call.on_receive(b"\xaa" * 7))

    adapter.tx_mock.reset_mock()

    if size != 0:
        segment_nr = ((size - 1) % 889) // 7 + 1
        cmd = 0x80 + segment_nr
        adapter.receive(
            0x602,
            cmd.to_bytes(1, "little")
            + b"\xAA" * ((size - 1) % 7 + 1)
            + bytes(6 - (size - 1) % 7),
        )
        handler_calls.append(call.on_receive(b"\xaa" * ((size - 1) % 7 + 1)))

        adapter.tx_mock.assert_called_once_with(
            0x582,
            b"\xA2" + segment_nr.to_bytes(1, "little") + b"\x7F\x00\x00\x00\x00\x00",
        )

    cmd = 0xC1 + ((6 - (size - 1) % 7) << 2)

    if crc and size:
        crc_bytes = struct.pack("<H", crc_hqx(b"\xAA" * size, 0))
    else:
        crc_bytes = bytes(2)

    adapter.tx_mock.reset_mock()
    adapter.receive(0x602, cmd.to_bytes(1, "little") + crc_bytes + bytes(5))
    handler_calls.append(call.on_finish())

    adapter.tx_mock.assert_called_once_with(0x582, b"\xA1" + bytes(7))

    if with_handler:
        assert n.object_dictionary.read(0x2000, 0) == b""
        assert handler_mock.mock_calls == handler_calls
    else:
        assert n.object_dictionary.read(0x2000, 0) == b"\xAA" * size


def test_sdo_block_failed():
    adapter = MockAdapter()
    n = Node(adapter, 0x02)

    # write 'const' and 'ro' variables
    adapter.receive(0x602, build_sdo_packet(cs=6, index=0x1200))  # const entry
    adapter.tx_mock.assert_called_with(0x582, b"\x80\x00\x12\x00\x02\x00\x01\x06")

    adapter.receive(0x602, build_sdo_packet(cs=6, index=0x1200, subindex=1))  # ro entry
    adapter.tx_mock.assert_called_with(0x582, b"\x80\x00\x12\x01\x02\x00\x01\x06")

    # wrong sequence number
    var = Variable(DT.DOMAIN, "rw")
    n.object_dictionary[0x2000] = var

    adapter.tx_mock.reset_mock()

    adapter.receive(0x602, b"\xC0\x00\x20\x00" + bytes(4))
    adapter.tx_mock.assert_called_once_with(0x582, b"\xa4\x00\x20\x00\x7f\x00\x00\x00")
    adapter.tx_mock.reset_mock()
    adapter.receive(0x602, b"\x00" + bytes(7))
    adapter.tx_mock.assert_called_once_with(0x582, b"\x80\x00\x20\x00\x03\x00\x04\x05")

    # block end with init
    adapter.tx_mock.reset_mock()

    adapter.receive(0x602, b"\xC1" + bytes(7))
    adapter.tx_mock.assert_called_once_with(0x582, b"\x80\x00\x00\x00\x01\x00\x04\x05")

    # wrong crc
    adapter.receive(0x602, b"\xC4\x00\x20\x00" + bytes(4))
    adapter.receive(0x602, b"\x81\xBB" + bytes(6))
    adapter.tx_mock.reset_mock()
    adapter.receive(0x602, b"\xD9" + bytes(7))
    adapter.tx_mock.assert_called_once_with(0x582, b"\x80\x00\x20\x00\x04\x00\x04\x05")

    # failed on_receive (1)
    adapter.tx_mock.reset_mock()

    handler_mock = Mock()
    handler_mock.on_receive.side_effect = ValueError()

    def download_handler(node, index, subindex, size):
        return handler_mock

    n.sdo_servers[0].download_manager.set_handler_callback(download_handler)

    adapter.receive(0x602, b"\xC4\x00\x20\x00" + bytes(4))
    adapter.receive(0x602, b"\x01\xBB" + bytes(6))
    adapter.tx_mock.assert_called_with(0x582, b"\x80\x00\x20\x00\x20\x00\x00\x08")


@pytest.mark.parametrize(
    "datatype",
    [
        DT.UNSIGNED8,
        DT.INTEGER8,
        DT.UNSIGNED16,
        DT.INTEGER16,
        DT.UNSIGNED32,
        DT.INTEGER32,
        DT.REAL32,
    ],
)
def test_sdo_upload_expetited(datatype):
    adapter = MockAdapter()
    n = Node(adapter, 0x02)

    value = struct_dict[datatype].unpack(
        b"\x01\x02\x03\x04"[: struct_dict[datatype].size]
    )[0]

    v = Variable(datatype, "rw", value=value)
    n.object_dictionary[0x2000] = v

    mock_write = Mock()
    n.object_dictionary.update_callbacks[(0x2000, 0)].add(mock_write)

    mock_write.assert_not_called()
    adapter.tx_mock.reset_mock()

    # with specified size
    size = struct_dict[datatype].size
    adapter.receive(0x602, b"\x40\x00\x20\x00\x00\x00\x00\x00")

    cmd = 0x43 + ((4 - size) << 2)
    adapter.tx_mock.assert_called_once_with(
        0x582,
        cmd.to_bytes(1, "little")
        + b"\x00\x20\x00"
        + b"\x01\x02\x03\x04"[:size]
        + bytes(4 - size),
    )


def test_sdo_upload_fails():
    adapter = MockAdapter()
    n = Node(adapter, 0x02)

    # read 'wo' variables
    v = Variable(DT.INTEGER8, "wo", value=0)
    n.object_dictionary[0x2000] = v

    adapter.receive(0x602, build_sdo_packet(cs=2, index=0x2000))  # wo entry
    adapter.tx_mock.assert_called_with(0x582, b"\x80\x00\x20\x00\x01\x00\x01\x06")

    # read not working
    v = Variable(DT.INTEGER8, "rw", value=0)
    n.object_dictionary[0x2001] = v

    def fail():
        raise ValueError("Validation failed")

    n.object_dictionary.set_read_callback(0x2001, 0, fail)
    adapter.receive(0x602, build_sdo_packet(cs=2, index=0x2001))
    adapter.tx_mock.assert_called_with(0x582, b"\x80\x01\x20\x00\x20\x00\x00\x08")


def test_upload_segmented():
    adapter = MockAdapter()
    n = Node(adapter, 0x02)

    v = Variable(DT.DOMAIN, "ro", value=b"ABCDEFGHIJKLMNO")
    n.object_dictionary[0x2000] = v

    adapter.receive(0x602, build_sdo_packet(cs=2, index=0x2000))  # init upload
    adapter.tx_mock.assert_called_with(
        0x582, b"\x41\x00\x20\x00\x0f\x00\x00\x00"
    )  # response to init upload

    adapter.receive(0x602, b"\x60\x00\x20\x00\x00\x00\x00\x00")  # first segment
    adapter.tx_mock.assert_called_with(
        0x582, b"\x00ABCDEFG"
    )  # response for first segment

    adapter.receive(0x602, b"\x70\x00\x20\x00\x00\x00\x00\x00")  # second segment
    adapter.tx_mock.assert_called_with(
        0x582, b"\x10HIJKLMN"
    )  # response for second segment

    adapter.receive(0x602, b"\x60\x00\x20\x00\x00\x00\x00\x00")  # third segment
    adapter.tx_mock.assert_called_with(
        0x582, b"\x0DO\x00\x00\x00\x00\x00\x00"
    )  # response for third segment


class UploadHandler(BaseUploadHandler):
    def __init__(self, data):
        self.data = data
        self.size = len(data)

    def on_read(self, size: int):
        response_data, self.data = self.data[:size], self.data[size:]
        return response_data


@pytest.mark.parametrize("with_handler", [True, False])
@pytest.mark.parametrize("size", [1, 2, 6, 7, 8, 14, 100])
@pytest.mark.parametrize("with_pst", [True, False])  # protocol switching threshold
def test_upload_segmented_various_length(with_handler, size, with_pst):
    adapter = MockAdapter()
    n = Node(adapter, 0x02)

    v = Variable(DT.DOMAIN, "ro", value=b"")
    n.object_dictionary[0x2000] = v

    def handler_callback(node: Node, index: int, subindex: int):
        if index == 0x2000:
            return UploadHandler(b"\xAA" * size)

    if with_handler:
        n.sdo_servers[0].upload_manager.set_handler_callback(handler_callback)
    else:
        n.object_dictionary.write(0x2000, 0, b"\xAA" * size, False)

    if with_pst:
        adapter.receive(
            0x602, struct.pack("<BHBBBH", 0xA0, 0x2000, 0, 127, size, 0)
        )  # init block upload with protocol switching threshold
    else:
        adapter.receive(
            0x602, build_sdo_packet(cs=2, index=0x2000)
        )  # init segmented upload

    if size <= 4:
        cmd = 0x43 + ((4 - size) << 2)
        data = b"\xAA" * size + bytes(4 - size)
        adapter.tx_mock.assert_called_with(
            0x582, cmd.to_bytes(1, "little") + b"\x00\x20\x00" + data
        )  # response to init upload (expitited)
        return

    adapter.tx_mock.assert_called_with(
        0x582, b"\x41\x00\x20\x00" + struct.pack("<I", size)
    )  # response to init upload

    toggle = False

    for _ in range((size - 1) // 7):
        cmd = 0x60 + (toggle << 4)

        adapter.receive(
            0x602, cmd.to_bytes(1, "little") + b"\x00\x20\x00\x00\x00\x00\x00"
        )  # request a segment
        adapter.tx_mock.assert_called_with(
            0x582, (toggle << 4).to_bytes(1, "little") + b"\xAA" * 7
        )  # response segment
        toggle = not toggle

    cmd = 0x60 + (toggle << 4)
    adapter.receive(
        0x602, cmd.to_bytes(1, "little") + b"\x00\x20\x00\x00\x00\x00\x00"
    )  # request last segment

    cmd = 0x01 + ((6 - ((size - 1) % 7)) << 1) + (toggle << 4)
    adapter.tx_mock.assert_called_with(
        0x582,
        cmd.to_bytes(1, "little")
        + b"\xAA" * ((size - 1) % 7 + 1)
        + b"\x00" * (6 - (size - 1) % 7),
    )  # response for last segment


@pytest.mark.parametrize("with_handler", [True, False])
def test_block_upload(with_handler):
    adapter = MockAdapter()
    n = Node(adapter, 0x02)

    v = Variable(DT.DOMAIN, "ro", value=b"ABCDEFGHIJKLMNO")
    n.object_dictionary[0x2000] = v

    def handler_callback(node: Node, index: int, subindex: int):
        if index == 0x2000:
            return UploadHandler(b"ABCDEFGHIJKLMNO")

    if with_handler:
        n.sdo_servers[0].upload_manager.set_handler_callback(handler_callback)

    adapter.receive(
        0x602, b"\xA4\x00\x20\x00\x02\x0D\x00\x00"
    )  # request block with crc, blocksize=2, pst=14
    adapter.tx_mock.assert_called_with(
        0x582, b"\xC6\x00\x20\x00\x0f\x00\x00\x00"
    )  # response to block upload init

    adapter.tx_mock.reset_mock()
    adapter.receive(0x602, b"\xA3" + bytes(7))  # request first part of block
    calls = [call(0x582, b"\x01ABCDEFG"), call(0x582, b"\x02HIJKLMN")]
    assert adapter.tx_mock.mock_calls == calls

    adapter.receive(
        0x602, b"\xA2\x02\x02" + bytes(5)
    )  # acknowledge fist part of blocks
    adapter.tx_mock.assert_called_with(
        0x582, b"\x81O" + bytes(6)
    )  # response for second part of blocks

    adapter.receive(
        0x602, b"\xA2\x01\x02" + bytes(5)
    )  # acknowledge second part of blocks
    crc = crc_hqx(b"ABCDEFGHIJKLMNO", 0)
    adapter.tx_mock.assert_called_with(
        0x582, b"\xD9" + crc.to_bytes(2, "little") + b"\x00\x00\x00\x00\x00"
    )  # response for third segment

    adapter.tx_mock.reset_mock()
    adapter.receive(0x602, b"\xA1" + bytes(7))  # acknowled transfer
    adapter.tx_mock.assert_not_called()


@pytest.mark.parametrize("size", [0, 1, 2, 6, 7, 8, 14, 100])
@pytest.mark.parametrize("blocksize", [1, 127])
@pytest.mark.parametrize("with_crc", [True, False])
@pytest.mark.parametrize(
    "with_handler, with_size", [(True, True), (True, False), (False, True)]
)
def test_block_upload_extended(size, blocksize, with_crc, with_handler, with_size):
    adapter = MockAdapter()
    n = Node(adapter, 0x02)

    data = (b"ABC" * (size // 3 + 1))[:size]
    crc = crc_hqx(data, 0) if with_crc else 0

    v = Variable(DT.DOMAIN, "ro", value=data)
    n.object_dictionary[0x2000] = v

    def handler_callback(node: Node, index: int, subindex: int):
        if index == 0x2000:
            handler = UploadHandler(data)
            if not with_size:
                handler.size = None
            return handler

    if with_handler:
        n.sdo_servers[0].upload_manager.set_handler_callback(handler_callback)

    cmd = 0xA0 + (with_crc << 2)
    pst = max(min(size - 1, 255), 0)
    adapter.receive(
        0x602, struct.pack("<BHBBBH", cmd, 0x2000, 0, blocksize, pst, 0)
    )  # request block with/without crc, various blocksize, pst=size-1

    size_response = size if with_size else 0
    cmd_response = 0xC4 + (with_size << 1)
    adapter.tx_mock.assert_called_with(
        0x582,
        cmd_response.to_bytes(1, "little")
        + b"\x00\x20\x00"
        + size_response.to_bytes(4, "little"),
    )  # response to block upload init

    adapter.tx_mock.reset_mock()
    adapter.receive(0x602, b"\xA3" + bytes(7))  # request upload block

    if not data:
        adapter.tx_mock.assert_called_with(
            0x582, (0x81).to_bytes(1, "little") + bytes(7)
        )
        adapter.receive(
            0x602, b"\xA2" + struct.pack("<BB", blocksize, blocksize) + bytes(5)
        )  # request next upload block

    while data:
        block_data, data = data[: blocksize * 7], data[blocksize * 7 :]
        slices = [block_data[i : i + 7] for i in range(0, len(block_data), 7)]

        calls = []

        for index, slice in enumerate(slices[:-1]):
            calls.append(call(0x582, (index + 1).to_bytes(1, "little") + slice))

        calls.append(
            call(
                0x582,
                (((not data) << 7) + len(slices)).to_bytes(1, "little")
                + slices[-1]
                + bytes(7 - len(slices[-1])),
            )
        )

        assert adapter.tx_mock.mock_calls == calls

        adapter.tx_mock.reset_mock()
        adapter.receive(
            0x602, b"\xA2" + struct.pack("<BB", blocksize, blocksize) + bytes(5)
        )  # request next upload block

    cmd = 0xC1 + ((7 - (size % 7)) << 2)
    adapter.tx_mock.assert_called_with(
        0x582, struct.pack("<BH", cmd, crc) + bytes(5)
    )  # response to last block upload requst
