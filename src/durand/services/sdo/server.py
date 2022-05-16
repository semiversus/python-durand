import struct
from enum import Enum
from typing import TYPE_CHECKING, Tuple
import logging

from durand.datatypes import DatatypeEnum as DT
from durand.object_dictionary import Variable, Record
from durand.services.nmt import StateEnum


if TYPE_CHECKING:
    from durand.node import Node


log = logging.getLogger(__name__)


SDO_STRUCT = struct.Struct("<BHB")


class SDODomainAbort(Exception):
    def __init__(self, code: int, multiplexor: Tuple[int, int] = None):
        Exception.__init__(self)
        self.code = code
        self.multiplexor = multiplexor


TransferState = Enum("TransferState", "NONE SEGMENT BLOCK BLOCK_END")


class SDOServer:
    def __init__(self, node: "Node", index=0):
        self._node = node
        self._index = index

        from .download import DownloadManager
        from .upload import UploadManager

        self.download_manager = DownloadManager(self)
        self.upload_manager = UploadManager(self)

        if index == 0:
            self._cob_rx = 0x600 + self._node.node_id
        else:
            self._cob_rx = 0x80000000

        if index == 0:
            self._cob_tx = 0x580 + self._node.node_id
        else:
            self._cob_tx = 0x80000000

        od = self._node.object_dictionary

        server_record = Record(name="SDO Server Parameter")
        server_record[1] = Variable(
            DT.UNSIGNED32,
            "rw" if index else "ro",
            self._cob_rx,
            name="COB-ID Client->Server (rx)",
        )
        server_record[2] = Variable(
            DT.UNSIGNED32,
            "rw" if index else "ro",
            self._cob_tx,
            name="COB-ID Server -> Client (tx)",
        )

        if index:
            od.update_callbacks[(0x1200 + index, 1)].add(self._update_cob_rx)
            od.update_callbacks[(0x1200 + index, 2)].add(self._update_cob_tx)
            server_record[3] = Variable(
                DT.UNSIGNED8, "rw", name="Node-ID of the SDO Client"
            )

            self._node.nmt.state_callbacks.add(self._update_subscription)
        else:
            self._node.nmt.state_callbacks.add(self._update_node)

        od[0x1200 + index] = server_record

    @property
    def node(self):
        return self._node

    def _update_subscription(self, state: StateEnum):
        if state == StateEnum.STOPPED:
            self._node.adapter.remove_subscription(self._cob_rx)
        elif state == StateEnum.PRE_OPERATIONAL and not (
            self._cob_rx | self._cob_tx
        ) & (1 << 31):
            self._node.adapter.add_subscription(self._cob_rx, self.handle_msg)

    def _update_node(self, state: StateEnum):
        if state == StateEnum.STOPPED:
            self._node.adapter.remove_subscription(self._cob_rx)
        elif state == StateEnum.PRE_OPERATIONAL:
            self._cob_rx = 0x600 + self._node.node_id
            self._cob_tx = 0x580 + self._node.node_id
            self._node.adapter.add_subscription(self._cob_rx, self.handle_msg)

    def _update_cob_rx(self, value: int):
        # bit 31: 0 - valid, 1 - invalid
        if not ((self._cob_rx | self._cob_tx) & (1 << 31)):
            self._node.adapter.remove_subscription(self._cob_rx & 0x7FF)

        if not value & (1 << 31) and not self._cob_tx & (1 << 31):
            self._node.adapter.add_subscription(value & 0x7FF, self.handle_msg)

        self._cob_rx = value

    def _update_cob_tx(self, value: int):
        # bit 31: 0 - valid, 1 - invalid
        if not ((self._cob_rx | self._cob_tx) & (1 << 31)) and value & (1 << 31):
            self._node.adapter.remove_subscription(self._cob_rx & 0x7FF)

        if not value & (1 << 31) and not self._cob_rx & (1 << 31):
            self._node.adapter.add_subscription(self._cob_rx & 0x7FF, self.handle_msg)

        self._cob_tx = value

    @property
    def cob_rx(self):
        if self._cob_rx & (1 << 31):
            return None

        return self._cob_rx

    @cob_rx.setter
    def cob_rx(self, cob: int):
        if cob is None:
            cob = 1 << 31

        self._node.object_dictionary.write(
            0x1200 + self._index, 1, cob, downloaded=False
        )

    @property
    def cob_tx(self):
        if self._cob_tx & (1 << 31):
            return None

        return self._cob_tx

    @cob_tx.setter
    def cob_tx(self, cob: int):
        if cob is None:
            cob = 1 << 31

        self._node.object_dictionary.write(
            0x1200 + self._index, 2, cob, downloaded=False
        )

    @property
    def client_node_id(self):
        return self._node.object_dictionary.read(0x1200 + self._index, 3)

    @client_node_id.setter
    def client_node_id(self, value):
        return self._node.object_dictionary.write(
            0x1200 + self._index, 3, value, downloaded=False
        )

    def handle_msg(self, cob_id: int, msg: bytes):
        assert (
            cob_id == self._cob_rx
        ), "Cob RX id invalid (0x{cob_id:X}, expected 0x{self._cob_rx:X})"

        try:
            ccs = (msg[0] & 0xE0) >> 5

            if msg[0] == 0x80:  # abort
                self.abort(msg)
            elif self.download_manager.block_transfer_active:
                self.download_manager.download_sub_block(msg)
            elif self.upload_manager.block_transfer_active:
                self.upload_manager.upload_sub_block(msg)
            elif ccs == 0:  # download segments
                self.download_manager.download_segment(msg)
            elif ccs == 1:  # init segmented download
                self.download_manager.init_download(msg)
            elif ccs == 2:  # init block upload
                self.upload_manager.init_upload(msg)
            elif ccs == 3:  # init segmented upload
                self.upload_manager.upload_segment(msg)
            elif ccs == 5 and msg[0] & 0x03 == 0:
                self.upload_manager.init_upload(msg)
            elif ccs == 6:  # init block download
                if msg[0] & 0x01:  # end block transfer
                    self.download_manager.download_block_end(msg)
                else:  # init block transfer
                    self.download_manager.download_block_init(msg)
            else:
                raise SDODomainAbort(0x05040001)  # SDO command not implemented
        except Exception as e:
            code = 0x08000000  # general error

            _, index, subindex = SDO_STRUCT.unpack(msg[:4])

            if isinstance(e, SDODomainAbort):
                code = e.code
                if e.multiplexor:
                    index, subindex = e.multiplexor
                elif e.multiplexor is False:
                    index, subindex = 0, 0
            else:
                log.exception("Exception during processing %r", msg)

            response = SDO_STRUCT.pack(0x80, index, subindex)
            response += struct.pack("<I", code)
            self._node.adapter.send(self._cob_tx, response)

    def lookup(self, index: int, subindex: int) -> Variable:
        try:
            return self._node.object_dictionary.lookup(index, subindex)
        except KeyError:
            try:
                self._node.object_dictionary.lookup(index, subindex=None)
            except KeyError:
                raise SDODomainAbort(0x06020000)  # object does not exist

        raise SDODomainAbort(0x06090011)  # subindex does not exist

    def abort(self, msg_data: bytes):
        _, index, subindex = SDO_STRUCT.unpack(msg_data[:4])

        try:
            variable = self._node.object_dictionary.lookup(index, subindex)
        except KeyError:
            return

        self.download_manager.on_abort((index, subindex))
        self.upload_manager.on_abort((index, subindex))
