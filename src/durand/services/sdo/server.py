import struct
from enum import Enum
from typing import TYPE_CHECKING
import logging

from durand.datatypes import DatatypeEnum as DT
from durand.object_dictionary import TMultiplexor, Variable, Record
from durand.services.nmt import StateEnum


if TYPE_CHECKING:
    from durand.node import Node


log = logging.getLogger(__name__)


SDO_STRUCT = struct.Struct("<BHB")


class SDODomainAbort(Exception):
    def __init__(self, code: int, multiplexor: TMultiplexor = None):
        Exception.__init__(self)
        self.code = code
        self.multiplexor = multiplexor


TransferState = Enum("TransferState", "NONE SEGMENT BLOCK BLOCK_END")


class SDOServer:
    def __init__(self, node: "Node", index=0):
        self._node = node
        self._index = index
        self._stopped = True

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

        self._handle_cs_dict = {
            0: self.download_manager.download_segment,
            1: self.download_manager.init_download,
            2: self.upload_manager.init_upload,
            3: self.upload_manager.upload_segment,
            5: self.upload_manager.init_upload,
            6: self._handle_download_block,
        }

    @property
    def node(self):
        return self._node

    def _update_subscription(self, state: StateEnum):
        if not self._stopped and state in (StateEnum.STOPPED, StateEnum.INITIALISATION):
            self._node.network.remove_subscription(self._cob_rx)
            self._stopped = True
            return

        if (
            self._stopped
            and state in (StateEnum.PRE_OPERATIONAL, StateEnum.OPERATIONAL)
            and not (self._cob_rx | self._cob_tx) & (1 << 31)
        ):
            self._node.network.add_subscription(self._cob_rx, self.handle_msg)
            self._stopped = False

    def _update_node(self, state: StateEnum):
        if not self._stopped and state in (StateEnum.STOPPED, StateEnum.INITIALISATION):
            self._node.network.remove_subscription(self._cob_rx)
            self._stopped = True
            return

        if self._stopped and state in (
            StateEnum.PRE_OPERATIONAL,
            StateEnum.OPERATIONAL,
        ):
            self._cob_rx = 0x600 + self._node.node_id
            self._cob_tx = 0x580 + self._node.node_id
            self._node.network.add_subscription(self._cob_rx, self.handle_msg)
            self._stopped = False

    def _update_cob_rx(self, value: int):
        # bit 31: 0 - valid, 1 - invalid
        if not (self._cob_rx | self._cob_tx) & (1 << 31):
            self._node.network.remove_subscription(self._cob_rx & 0x7FF)

        if not value & (1 << 31) and not self._cob_tx & (1 << 31):
            self._node.network.add_subscription(value & 0x7FF, self.handle_msg)

        self._cob_rx = value

    def _update_cob_tx(self, value: int):
        # bit 31: 0 - valid, 1 - invalid
        if not ((self._cob_rx | self._cob_tx) & (1 << 31)) and value & (1 << 31):
            self._node.network.remove_subscription(self._cob_rx & 0x7FF)

        if not value & (1 << 31) and not self._cob_rx & (1 << 31):
            self._node.network.add_subscription(self._cob_rx & 0x7FF, self.handle_msg)

        self._cob_tx = value

    @property
    def cob_rx(self) -> int:
        if self._cob_rx & (1 << 31):
            return None

        return self._cob_rx

    @cob_rx.setter
    def cob_rx(self, cob: int):
        if cob is None:
            cob = 1 << 31

        self._node.object_dictionary.write(0x1200 + self._index, 1, cob)

    @property
    def cob_tx(self) -> int:
        if self._cob_tx & (1 << 31):
            return None

        return self._cob_tx

    @cob_tx.setter
    def cob_tx(self, cob: int):
        if cob is None:
            cob = 1 << 31

        self._node.object_dictionary.write(0x1200 + self._index, 2, cob)

    @property
    def client_node_id(self) -> int:
        return self._node.object_dictionary.read(0x1200 + self._index, 3)

    @client_node_id.setter
    def client_node_id(self, value: int):
        return self._node.object_dictionary.write(0x1200 + self._index, 3, value)

    def handle_msg(self, cob_id: int, msg: bytes) -> None:
        assert (
            cob_id == self._cob_rx
        ), "Cob RX id invalid (0x{cob_id:X}, expected 0x{self._cob_rx:X})"

        try:    
            ccs = (msg[0] & 0xE0) >> 5

            if msg[0] == 0x80:  # abort
                return self.abort(msg)
            if self.download_manager.block_transfer_active:
                return self.download_manager.download_sub_block(msg)
            if self.upload_manager.block_transfer_active:
                return self.upload_manager.upload_sub_block(msg)
            # TODO: handle active download or upload by a state machine

            try:
                return self._handle_cs_dict[ccs](msg)
            except KeyError as exc:  # ccs not found
                raise SDODomainAbort(0x05040001) from exc  # SDO command not implemented
        except SDODomainAbort as exc:
            index, subindex = 0, 0
            if exc.multiplexor:
                index, subindex = exc.multiplexor
            response = SDO_STRUCT.pack(0x80, index, subindex)
            response += struct.pack("<I", exc.code)
            self._node.network.send(self._cob_tx, response)
        except Exception as exc:
            if len(msg) >= 4:
                _, index, subindex = SDO_STRUCT.unpack(msg[:4])
            else:
                index, subindex = (0,0)
                
            # TODO: use index, subindex only when available in msg
            log.debug(f"{exc!r} during processing {msg!r}")

            response = SDO_STRUCT.pack(0x80, index, subindex) + b"\x00\x00\x00\x08"
            self._node.network.send(self._cob_tx, response)  # report general error

    def _handle_download_block(self, msg: bytes):
        if msg[0] & 0x01:  # end block transfer
            self.download_manager.download_block_end(msg)
        else:  # init block transfer
            self.download_manager.download_block_init(msg)

    def lookup(self, index: int, subindex: int) -> Variable:
        try:
            variable = self._node.object_dictionary.lookup(index, subindex)
            assert isinstance(variable, Variable), "Variable expected"
            return variable
        except KeyError:
            try:
                self._node.object_dictionary.lookup(index, subindex=None)
            except KeyError as exc:
                raise SDODomainAbort(
                    0x06020000, multiplexor=(index, subindex)
                ) from exc  # object does not exist

        raise SDODomainAbort(
            0x06090011, multiplexor=(index, subindex)
        )  # subindex does not exist

    def abort(self, msg_data: bytes):
        _, index, subindex = SDO_STRUCT.unpack(msg_data[:4])

        try:
            self._node.object_dictionary.lookup(index, subindex)
        except KeyError:
            # if index:subindex not available - there is nothing to abort
            return

        self.download_manager.on_abort((index, subindex))
        self.upload_manager.on_abort((index, subindex))
