import struct
from binascii import crc_hqx
from typing import Tuple

from .server import SDODomainAbort, SDOServer, TransferState, SDO_STRUCT


class BaseDownloadHandler:
    def on_receive(self, data: bytes):
        """on_received is called when new data is received

        :param data: bytes received and to be appended
        """

    def on_finish(self):
        """on_finish is called when the transfer is successfully completed"""

    def on_abort(self):
        """on_abort is called when the transfer was aborted"""


class DownloadManager:
    def __init__(self, server: SDOServer):
        self._server = server

        self._handler_callback = None
        self._handler: BaseDownloadHandler = None

        self._multiplexor: Tuple[int, int] = None
        self._state = TransferState.NONE

        self._buffer = bytearray()

        # used for block transfer
        self._sequence_number = None
        self._crc = None

        # used for segmented transfer
        self._toggle_bit = None

    def set_handler_callback(self, callback):
        self._handler_callback = callback

    @property
    def block_transfer_active(self):
        return self._state == TransferState.BLOCK

    def _init(self, new_state: TransferState):
        self._state = new_state

        self._handler = None
        self._sequence_number = None
        self._toggle_bit = False
        self._buffer.clear()

    def on_abort(self, multiplexor):
        if self._state != TransferState.NONE and self._multiplexor == multiplexor:
            self._abort()

    def _receive(self, data: bytes):
        if self._handler:
            try:
                self._handler.on_receive(data)
            except:
                self._abort()
                raise SDODomainAbort(
                    0x08000020, self._multiplexor
                )  # data can't be stored
        else:
            self._buffer.extend(data)

    def _abort(self):
        if self._handler:
            self._handler.on_abort()

        self._init(TransferState.NONE)

    def _finish(self):
        try:
            if self._handler:
                self._handler.on_finish()
            else:
                variable = self._server.lookup(*self._multiplexor)
                value = variable.unpack(self._buffer)

                if variable.minimum is not None and value < variable.minimum:
                    raise SDODomainAbort(0x06090032, self._multiplexor)  # value too low

                if variable.maximum is not None and value > variable.maximum:
                    raise SDODomainAbort(
                        0x06090031, self._multiplexor
                    )  # value too high

                self._server.node.object_dictionary.write(*self._multiplexor, value)
        except struct.error:
            raise SDODomainAbort(
                0x06070010, self._multiplexor
            )  # datatype size is not matching
        except SDODomainAbort as e:
            raise e
        except Exception as e:
            raise SDODomainAbort(0x08000020, self._multiplexor)  # data can't be stored
        finally:
            self._init(TransferState.NONE)

    def init_download(self, msg: bytes):
        if self._state != TransferState.NONE:
            self._abort()

        cmd, index, subindex = SDO_STRUCT.unpack(msg[:4])

        variable = self._server.lookup(index, subindex)

        if variable.access not in ("rw", "wo"):
            raise SDODomainAbort(0x06010002)  # write a read-only object

        response = SDO_STRUCT.pack(0x60, index, subindex) + bytes(4)

        if not cmd & 0x02:  # segmented transfer (not expitited)
            self._init(TransferState.SEGMENT)
            self._multiplexor = (index, subindex)

            if cmd & 0x01:  # size specified
                size = int.from_bytes(msg[4:], "little")
            else:
                size = None

            if self._handler_callback:
                self._handler = self._handler_callback(
                    self._server.node, index, subindex, size
                )

            self._server.node.adapter.send(self._server.cob_tx, response)
            return

        if cmd & 0x01:  # size specified
            size = 4 - ((cmd >> 2) & 0x03)
        else:
            size = variable.size

        self._init(TransferState.NONE)

        if self._handler_callback:
            self._handler = self._handler_callback(
                self._server.node, index, subindex, size
            )

        self._multiplexor = (index, subindex)
        self._receive(msg[4 : 4 + size])
        self._finish()

        self._server.node.adapter.send(self._server.cob_tx, response)

    def download_segment(self, msg: bytes):
        if self._state != TransferState.SEGMENT:
            self._abort()
            raise SDODomainAbort(
                0x05040001, multiplexor=False
            )  # client command specificer not valid

        toggle_bit = bool(msg[0] & 0x10)

        if toggle_bit != self._toggle_bit:
            self._abort()
            raise SDODomainAbort(
                0x05030000, self._multiplexor
            )  # toggle bit not altered

        self._toggle_bit = not self._toggle_bit

        size = 7 - ((msg[0] & 0x0E) >> 1)

        self._receive(msg[1 : 1 + size])

        if msg[0] & 0x01:  # check continue bit
            self._finish()

        cmd = 0x20 + (toggle_bit << 4)
        self._server.node.adapter.send(
            self._server.cob_tx, cmd.to_bytes(1, "little") + bytes(7)
        )

    def download_block_init(self, msg: bytes):
        if self._state != TransferState.NONE:
            self._abort()

        cmd, index, subindex = SDO_STRUCT.unpack(msg[:4])

        variable = self._server.lookup(index, subindex)

        if variable.access not in ("rw", "wo"):
            raise SDODomainAbort(0x06010002)  # write a read-only object

        self._init(TransferState.BLOCK)
        self._multiplexor = (index, subindex)

        self._crc = 0 if cmd & 0x04 else None

        if cmd & 0x02:  # size bit
            size = struct.unpack("<I", msg[4:])
        else:
            size = None

        if self._handler_callback:
            self._handler = self._handler_callback(
                self._server.node, index, subindex, size
            )

        self._sequence_number = 1

        cmd = 0xA4
        self._server.node.adapter.send(
            self._server.cob_tx,
            cmd.to_bytes(1, "little") + msg[1:4] + b"\x7F" + bytes(3),
        )

    def download_sub_block(self, msg: bytes):
        if self._sequence_number != msg[0] & 0x7F:
            self._abort()
            raise SDODomainAbort(
                0x05040003, self._multiplexor
            )  # invalid sequence number

        last_sub_block = bool(msg[0] & 0x80)

        data = msg[1:]

        if self._crc is not None and not last_sub_block:
            self._crc = crc_hqx(data, self._crc)

        if not last_sub_block:
            self._receive(data)
        else:
            self._buffer.extend(data)
            self._state = TransferState.BLOCK_END

        if self._sequence_number == 127 or last_sub_block:
            self._server.node.adapter.send(
                self._server.cob_tx,
                b"\xA2"
                + self._sequence_number.to_bytes(1, "little")
                + b"\x7F"
                + bytes(5),
            )
            self._sequence_number = 1
        else:
            self._sequence_number += 1

    def download_block_end(self, msg: bytes):
        if self._state != TransferState.BLOCK_END:
            self._abort()
            raise SDODomainAbort(
                0x05040001, multiplexor=False
            )  # client command specificer not valid

        size = 7 - ((msg[0] >> 2) & 0x07)

        if self._crc is not None:
            self._crc = crc_hqx(self._buffer[-7:][:size], self._crc)
            if self._crc != struct.unpack("<H", msg[1:3])[0]:
                self._abort()
                raise SDODomainAbort(0x05040004, self._multiplexor)  # CRC invalid

        if self._handler:
            self._receive(self._buffer[:size])
        elif size != 7:
            del self._buffer[size % 7 - 7 :]

        self._finish()

        self._server.node.adapter.send(self._server.cob_tx, b"\xA1" + bytes(7))
