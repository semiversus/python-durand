import struct
from typing import TYPE_CHECKING
import logging

from durand.datatypes import DatatypeEnum as DT
from durand.object_dictionary import Variable

if TYPE_CHECKING:
    from durand.node import Node


log = logging.getLogger(__name__)


SDO_STRUCT = struct.Struct('<BHB')


class SDODomainAbort(Exception):
    def __init__(self, code: int):
        Exception.__init__(self)
        self.code = code


class SDOServer:
    def __init__(self, node: 'Node', index=0, cob_rx: int=None, cob_tx: int=None):
        self._node = node

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
            od.add_download_callback(cob_rx, self._update_cob_rx)
            od.add_download_callback(cob_tx, self._update_cob_tx)

            od.add_object(Variable(0x1200 + index, 3, DT.UNSIGNED8, 'rw'))
        
        self._node.add_subscription(self._cob_rx, self.handle_msg)

    def _update_cob_rx(self, value: int):
        # bit 31: 0 - valid, 1 - invalid
        if ((self._cob_rx & self._cob_tx) & (1 << 31)) and not value & (1 << 31):
            self._node.remove_subscription(self._cob_rx & 0x7FF)

        if not self._cob_rx & (1 << 31) and value & (1 << 31) and self._cob_tx & (1 << 31):
            self._node.add_subscription(value & 0x7FF)

        self._cob_rx = value

    def _update_cob_tx(self, value: int):
        # bit 31: 0 - valid, 1 - invalid
        if ((self._cob_rx & self._cob_tx) & (1 << 31)) and not value & (1 << 31):
            self._node.remove_subscription(self._cob_rx & 0x7FF)

        if not self._cob_tx & (1 << 31) and value & (1 << 31) and self._cob_rx & (1 << 31):
            self._node.add_subscription(self._cob_rx & 0x7FF)

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
        try:
            ccs = msg[0] & 0xE0
            if ccs == 0x20:  # request download
                self.init_download(msg)
            elif ccs == 0x40:  # request upload
                self.init_upload(msg)
            else:
                raise SDODomainAbort(0x05040001)  # SDO command not implemented
        except Exception as e:
            code = 0x08000000  # general error
            if isinstance(e, SDODomainAbort):
                code = e.code
            else:
                log.exception('Exception during processing %r', msg)

            _, index, subindex = SDO_STRUCT.unpack(msg[:4])
            response = SDO_STRUCT.pack(0x80, index, subindex)
            response += struct.pack('<I', code)
            self._node.adapter.send(self._cob_tx, response)

    def _lookup(self, index: int, subindex: int) -> Variable:
        try:
            return self._node.object_dictionary.lookup(index, subindex)
        except KeyError:
            try:
                self._node.object_dictionary.lookup(index, 0)
            except KeyError:
                raise SDODomainAbort(0x06020000)  # object does not exist

        raise SDODomainAbort(0x06090011)  # subindex does not exist

    def init_download(self, msg: bytes):
        cmd, index, subindex = SDO_STRUCT.unpack(msg[:4])

        if not cmd & 0x02:  # expedited transfer
            raise SDODomainAbort(0x05040001)  # SDO command not implemented

        variable = self._lookup(index, subindex)

        if variable.access not in ('rw', 'wo'):
            raise SDODomainAbort(0x06010002)  # write a read-only object

        if cmd & 0x01:  # size specified
            size = 4 - ((cmd >> 2) & 0x03)
        else:
            size = variable.size

        try:
            value = variable.unpack(msg[4:4+size])
        except struct.error:
            raise SDODomainAbort(0x06070010)  # datatype size is not matching

        if variable.minimum is not None and value < variable.minimum:
            raise SDODomainAbort(0x06090032)  # value too low

        if variable.maximum is not None and value > variable.maximum:
            raise SDODomainAbort(0x06090031)  # value too high

        try:
            self._node.object_dictionary.write(variable, value)
        except Exception:
            raise SDODomainAbort(0x08000020)  # data can't be stored

        response = SDO_STRUCT.pack(0x60, index, subindex) + bytes(4)
        self._node.adapter.send(self._cob_tx, response)

    def init_upload(self, msg_data: bytes):
        _, index, subindex = SDO_STRUCT.unpack(msg_data[:4])

        variable = self._lookup(index, subindex)

        if variable.access not in ('ro', 'rw', 'constant'):
            raise SDODomainAbort(0x06010001)  # read a write-only object

        value = self._node.object_dictionary.read(variable)
        try:
            data = variable.pack(value)
        except struct.error:
            raise SDODomainAbort(0x06090030)  # value range exceeded

        cmd = 0x43 + ((4 - variable.size) << 2)

        response = SDO_STRUCT.pack(cmd, index, subindex) + data
        response += bytes(4 - variable.size)

        self._node.adapter.send(self._cob_tx, response)
