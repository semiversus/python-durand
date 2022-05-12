import struct
from typing import Tuple
from binascii import crc_hqx

from durand.datatypes import is_numeric

from .server import SDODomainAbort, SDOServer, TransferState, SDO_STRUCT


class BaseUploadHandler:
    size = None

    def on_read(self, size: int) -> bytes:
        """on_read is called when new data is requested

        :param size: number of bytes to be read
        :returns: next slice of data
        """

    def on_finish(self):
        """on_finish is called when the transfer is successfully completed"""

    def on_abort(self) -> None:
        """on_abort is called when the transfer was aborted"""


class HandlerStream:
    def __init__(self, upload_handler: BaseUploadHandler):
        self._handler = upload_handler
        self.size = upload_handler.size
        self._buffer = bytearray()

    def _extend(self, size: int):
        missing_bytes = size - len(self._buffer)

        if missing_bytes > 0:
            self._buffer.extend(self._handler.on_read(missing_bytes))

    def peek(self, size: int) -> bytes:
        self._extend(size)
        return self._buffer[:size]

    def read(self, size: int) -> bytes:
        self._extend(size)
        data = self._buffer[:size]
        del self._buffer[:size]
        return data

    def abort(self):
        self._handler.on_abort()
        self._buffer.clear()

    def release(self):
        self._handler.on_finish()
        self._buffer.clear()


class FixedStream:
    def __init__(self, data: bytes):
        self._buffer = memoryview(data)
        self.size = len(self._buffer)

    def peek(self, size: int) -> bytes:
        return bytes(self._buffer[:size])

    def read(self, size: int) -> bytes:
        data = bytes(self._buffer[:size])
        self._buffer = self._buffer[size:]
        return data

    def abort(self):
        self._buffer.release()

    def release(self):
        self._buffer.release()


class UploadManager:
    def __init__(self, server: SDOServer):
        self._server = server

        self._handler_callback = None

        self._multiplexor: Tuple[int, int] = None
        self._state = TransferState.NONE

        # used for block transfer
        self._block_size = None
        self._crc = None

        # used for segmented transfer
        self._toggle_bit = None

    def set_handler_callback(self, callback):
        self._handler_callback = callback

    @property
    def block_transfer_active(self):
        return self._state in (TransferState.BLOCK, TransferState.BLOCK_END)

    def on_abort(self, multiplexor):
        if self._state != TransferState.NONE and self._multiplexor == multiplexor:
            self._abort()

    def _abort(self):
        if self._stream:
            self._stream.abort()
        self._stream = None
        self._state = TransferState.NONE

    def setup(self, index, subindex) -> int:
        variable = self._server.lookup(index, subindex)

        if variable.access == "wo":
            raise SDODomainAbort(0x06010001)  # read a write-only object

        self._multiplexor = (index, subindex)

        if self._handler_callback:
            handler = self._handler_callback(self._server.node, index, subindex)

            if handler:
                self._stream = HandlerStream(handler)
                return

        try:
            value = self._server.node.object_dictionary.read(index, subindex)
        except:
            raise SDODomainAbort(
                0x08000020, self._multiplexor
            )  # data can't be transferred

        if is_numeric(variable.datatype):
            value = variable.pack(value)

        self._stream = FixedStream(value)

    def init_upload(self, msg: bytes):
        if self._state != TransferState.NONE:
            self._abort()

        cmd, index, subindex = SDO_STRUCT.unpack(msg[:4])

        self.setup(index, subindex)
        size = self._stream.size

        if msg[0] & 0xE3 == 0xA0 and (
            msg[5] == 0 or size is None or size > msg[5]
        ):  # ccs=5, cs=0 -> block upload
            # msg[5] is protocol switching threshold
            self._state = TransferState.BLOCK
            self._crc = 0 if msg[0] & 0x04 else None

            size_bytes = struct.pack("<I", size) if size is not None else bytes(4)

            self._block_size = msg[4]

            cmd = 0xC4 if size is None else 0xC6
            self._server.node.adapter.send(
                self._server.cob_tx, cmd.to_bytes(1, "little") + msg[1:4] + size_bytes
            )
            return

        if size is not None and size <= 4:
            # make an expetited transfer
            data = self._stream.read(4)
            self._stream.release()
            self._stream = None
            cmd = 0x43 + ((4 - len(data)) << 2)
            response = (
                SDO_STRUCT.pack(cmd, index, subindex) + data + bytes(4 - len(data))
            )
            self._server.node.adapter.send(self._server.cob_tx, response)
            return

        self._state = TransferState.SEGMENT
        self._toggle_bit = False

        cmd = 0x40 + (size is not None)
        size_bytes = struct.pack("<I", size) if size is not None else bytes(4)

        self._server.node.adapter.send(
            self._server.cob_tx, cmd.to_bytes(1, "little") + msg[1:4] + size_bytes
        )

    def upload_segment(self, msg: bytes):
        if self._state != TransferState.SEGMENT:
            self._abort()
            raise SDODomainAbort(
                0x05040001, variable=False
            )  # client command specificer not valid

        toggle_bit = bool(msg[0] & 0x10)

        if toggle_bit != self._toggle_bit:
            self._abort()
            raise SDODomainAbort(
                0x05030000, self._multiplexor
            )  # toggle bit not altered

        self._toggle_bit = not self._toggle_bit

        data = self._stream.read(7)
        no_data_left = not self._stream.peek(1)

        if no_data_left:
            self._state = TransferState.NONE
            self._stream.release()
            self._stream = None

        cmd = (toggle_bit << 4) + no_data_left + ((7 - len(data)) << 1)

        self._server.node.adapter.send(
            self._server.cob_tx, cmd.to_bytes(1, "little") + data + bytes(7 - len(data))
        )

    def upload_sub_block(self, msg: bytes):
        if self._state == TransferState.BLOCK_END:
            self._stream.release()
            self._stream = None
            self._state = TransferState.NONE
            return

        if self._state != TransferState.BLOCK:
            self._abort()
            raise SDODomainAbort(
                0x05040001, variable=None
            )  # client command specificer not valid

        if msg[0] & 0x03 == 2:
            data = self._stream.read(msg[1] * 7)
            if self._crc is not None:
                self._crc = crc_hqx(data, self._crc)

            self._block_size = msg[2]

            if not self._stream.peek(1):
                cmd = 0xC1 + ((7 - len(data) % 7) << 2)
                crc = self._crc if self._crc is not None else 0
                self._server.node.adapter.send(
                    self._server.cob_tx,
                    cmd.to_bytes(1, "little") + crc.to_bytes(2, "little") + bytes(5),
                )
                self._state = TransferState.BLOCK_END
                return

        data = self._stream.peek(self._block_size * 7 + 1)
        data, following_byte = (
            data[: self._block_size * 7],
            data[self._block_size * 7 :],
        )
        chunks = [data[i : i + 7] for i in range(0, len(data), 7)]

        for index, chunk in enumerate(chunks[:-1]):
            response = (index + 1).to_bytes(1, "little") + chunk
            self._server.node.adapter.send(self._server.cob_tx, response)

        last_block = not following_byte
        first_byte = (last_block << 7) + (len(chunks) if chunks else 1)
        data = chunks[-1] if chunks else b""
        response = first_byte.to_bytes(1, "little") + data + bytes(7 - len(data))
        self._server.node.adapter.send(self._server.cob_tx, response)
