import struct
from enum import Enum
from typing import TYPE_CHECKING
import logging

from durand.datatypes import DatatypeEnum as DT
from durand.object_dictionary import Variable


if TYPE_CHECKING:
    from durand.node import Node


log = logging.getLogger(__name__)


SDO_STRUCT = struct.Struct('<BHB')


class SDODomainAbort(Exception):
    def __init__(self, code: int, variable: Variable = None):
        Exception.__init__(self)
        self.code = code
        self.variable = variable


TransferState = Enum('TransferState', 'NONE SEGMENT BLOCK BLOCK_END')
        

class SDOServer:
    def __init__(self, node: 'Node', index=0, cob_rx: int=None, cob_tx: int=None):
        self._node = node
        
        from .download import DownloadManager
        self.download_manager = DownloadManager(self)

        if cob_rx is None:
            self._cob_rx = 0x80000000
        else:
            self._cob_rx = cob_rx

        if cob_tx is None:
            self._cob_tx = 0x80000000
        else:
            self._cob_tx = cob_tx

        od = self._node.object_dictionary
        od.add_object(Variable(0x1200 + index, 0, DT.UNSIGNED8,
                      'const', 3 if index else 2))

        cob_rx_var = Variable(0x1200 + index, 1, DT.UNSIGNED32,
                             'rw' if index else 'ro', self._cob_rx)
        od.add_object(cob_rx_var)

        cob_tx_var = Variable(0x1200 + index, 2, DT.UNSIGNED32,
                             'rw' if index else 'ro', self._cob_tx)
        od.add_object(cob_tx_var)

        if index:
            od.download_callbacks[cob_rx].add(self._update_cob_rx)
            od.download_callbacks[cob_tx].add(self._update_cob_tx)

            od.add_object(Variable(0x1200 + index, 3, DT.UNSIGNED8, 'rw'))

        self._node.adapter.add_subscription(self._cob_rx, self.handle_msg)

    @property
    def node(self):
        return self._node

    def _update_cob_rx(self, value: int):
        # bit 31: 0 - valid, 1 - invalid
        if ((self._cob_rx & self._cob_tx) & (1 << 31)) and not value & (1 << 31):
            self._node.remove_subscription(self._cob_rx & 0x7FF)

        if not self._cob_rx & (1 << 31) and value & (1 << 31) and self._cob_tx & (1 << 31):
            self._node.adapter.add_subscription(value & 0x7FF)

        self._cob_rx = value

    def _update_cob_tx(self, value: int):
        # bit 31: 0 - valid, 1 - invalid
        if ((self._cob_rx & self._cob_tx) & (1 << 31)) and not value & (1 << 31):
            self._node.remove_subscription(self._cob_rx & 0x7FF)

        if not self._cob_tx & (1 << 31) and value & (1 << 31) and self._cob_rx & (1 << 31):
            self._node.adapter.add_subscription(self._cob_rx & 0x7FF)

        self._cob_rx = value

    @property
    def cob_tx(self):
        if self._cob_tx & (1 << 31):
            return None

        return self._cob_tx

    @cob_tx.setter
    def cob_tx(self, cob: int):
        if cob is None:
            self._update_cob_tx(1 << 31)
        else:
            self._update_cob_tx(cob)

    @property
    def cob_rx(self):
        if self._cob_rx & (1 << 31):
            return None

        return self._cob_rx

    @cob_rx.setter
    def cob_rx(self, cob: int):
        if cob is None:
            self._update_cob_rx(1 << 31)
        else:
            self._update_cob_rx(cob)

    def handle_msg(self, cob_id: int, msg: bytes):
        assert cob_id == self._cob_rx, 'Cob RX id invalid (0x{cob_id:X}, expected 0x{self._cob_rx:X})'
        
        try:
            ccs = (msg[0] & 0xE0) >> 5

            if msg[0] == 0x80:  # abort
                self.abort(msg)
            elif self.download_manager.block_transfer_active:
                self.download_manager.download_sub_block(msg)
            elif ccs == 0:  # download segments
                self.download_manager.download_segment(msg)
            elif ccs == 1:  # init download
                self.download_manager.init_download(msg)
            elif ccs == 2:  # init upload
                self.init_upload(msg)
            elif ccs == 6:  # init/end download block
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
                if e.variable:
                    index, subindex = e.variable.multiplexor
                elif e.variable is False:
                    index, subindex = 0, 0
            else:
                log.exception('Exception during processing %r', msg)

            response = SDO_STRUCT.pack(0x80, index, subindex)
            response += struct.pack('<I', code)
            self._node.adapter.send(self._cob_tx, response)

    def lookup(self, index: int, subindex: int) -> Variable:
        try:
            return self._node.object_dictionary.lookup(index, subindex)
        except KeyError:
            try:
                self._node.object_dictionary.lookup(index, 0)
            except KeyError:
                raise SDODomainAbort(0x06020000)  # object does not exist

        raise SDODomainAbort(0x06090011)  # subindex does not exist

    def init_upload(self, msg_data: bytes):
        _, index, subindex = SDO_STRUCT.unpack(msg_data[:4])

        variable = self.lookup(index, subindex)

        if variable.access not in ('ro', 'rw', 'constant'):
            raise SDODomainAbort(0x06010001)  # read a write-only object

        try:
            value = self._node.object_dictionary.read(variable)
            data = variable.pack(value)
        except Exception:
            log.exception(f'Exception while reading {variable}')
            raise SDODomainAbort(0x06060000)  # access failed

        cmd = 0x43 + ((4 - variable.size) << 2)

        response = SDO_STRUCT.pack(cmd, index, subindex) + data
        response += bytes(4 - variable.size)

        self._node.adapter.send(self._cob_tx, response)
    
    def abort(self, msg_data: bytes):
        _, index, subindex = SDO_STRUCT.unpack(msg_data[:4])
        
        try:
            variable = self._node.object_dictionary.lookup(index, subindex)
        except KeyError:
            return

        self.download_manager.on_abort(variable)
        
