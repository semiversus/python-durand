import struct
from typing import TYPE_CHECKING
import logging

from durand.datatypes import DatatypeEnum as DT
from durand.datatypes import struct_dict
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
    def __init__(self, node: 'Node', index=0):
        self._node = node
        self._index = index

        if index:
            self._cob_rxsdo = 0x80000000
            self._cob_txsdo = 0x80000000
        else:
            self._cob_rxsdo = 0x600 + node.node_id
            self._cob_txsdo = 0x580 + node.node_id

        od = self._node.object_dictionary
        od.add_object(Variable(0x1200 + index, 0, DT.UNSIGNED8,
                      'const', 3 if index else 2))

        cob_rxsdo = Variable(0x1200 + index, 1, DT.UNSIGNED32,
                             'rw' if index else 'const', self._cob_rxsdo)
        od.add_object(cob_rxsdo)

        cob_txsdo = Variable(0x1200 + index, 2, DT.UNSIGNED32,
                             'rw' if index else 'const', self._cob_txsdo)
        od.add_object(cob_txsdo)

        if index:
            od.add_update_callback(cob_rxsdo, self._update_cob_rxsdo)
            od.add_update_callback(cob_txsdo, self._update_cob_txsdo)
        else:
            od.add_object(Variable(0x1200 + index, 3, DT.UNSIGNED8,
                                   'rw' if index else 'ro'))
            self._node.add_subscription(self._cob_rxsdo, self.handle_msg)

    def _update_cob_rxsdo(self, value: int):
        # bit 31: 0 - valid, 1 - invalid
        if not (self._cob_rxsdo | self._cob_txsdo) & (1 << 31):
            self._node.remove_subscription(self._cob_rxsdo & 0x7FF)

        self._cob_rxsdo = value

        if not (value | self._cob_txsdo) & (1 << 31):
            self._node.add_subscription(value & 0x7FF)

    def _update_cob_txsdo(self, value: int):
        # bit 31: 0 - valid, 1 - invalid
        if not (self._cob_rxsdo | self._cob_txsdo) & (1 << 31):
            self._node.remove_subscription(self._cob_rxsdo & 0x7FF)

        self._cob_txsdo = value

        if not (value | self._cob_rxsdo) & (1 << 31):
            self._node.add_subscription(self._cob_rxsdo & 0x7FF)

    def handle_msg(self, cob_id: int, msg: bytes):
        try:
            ccs = msg[0] & 0xE0
            if ccs == 0x20:  # request download
                self.download(msg)
            elif ccs == 0x40:  # request upload
                self.upload(msg)
            else:
                raise SDODomainAbort(0x05040001)  # SDO command not implemented
        except Exception as e:
            code = 0x08000000  # general error
            if isinstance(e, SDODomainAbort):
                code = e.code

            log.exception('Exception during processing %r', msg)

            _, index, subindex = SDO_STRUCT.unpack(msg[:4])
            response = SDO_STRUCT.pack(0x80, index, subindex)
            response += struct.pack('<I', code)
            self._node.adapter.send(self._cob_txsdo, response)

    def _lookup(self, index: int, subindex: int) -> Variable:
        try:
            return self._node.object_dictionary.lookup(index, subindex)
        except KeyError:
            try:
                self._node.object_dictionary.lookup(index, 0)
            except KeyError:
                raise SDODomainAbort(0x06020000)  # object does not exist

        raise SDODomainAbort(0x06090011)  # subindex does not exist

    def download(self, msg: bytes):
        cmd, index, subindex = SDO_STRUCT.unpack(msg[:4])

        if not cmd & 0x02:  # expedited transfer
            raise SDODomainAbort(0x05040001)  # SDO command not implemented

        variable = self._lookup(index, subindex)

        if variable.access not in ('rw', 'wo'):
            raise SDODomainAbort(0x06010002)  # write a read-only object

        dt_struct = struct_dict[variable.datatype]

        if cmd & 0x01:  # size specified
            size = 4 - ((cmd >> 2) & 0x03)
        else:
            size = dt_struct.size

        try:
            value, = dt_struct.unpack(msg[4:4+size])
        except struct.error:
            raise SDODomainAbort(0x06070010)  # datatype size is not matching

        value *= variable.factor

        if variable.minimum is not None and value < variable.minimum:
            raise SDODomainAbort(0x06090032)  # value too low

        if variable.maximum is not None and value > variable.maximum:
            raise SDODomainAbort(0x06090031)  # value too high

        try:
            self._node.object_dictionary.write(variable, value)
        except Exception:
            raise SDODomainAbort(0x08000020)  # data can't be stored

        response = SDO_STRUCT.pack(0x60, index, subindex) + bytes(4)
        self._node.adapter.send(self._cob_txsdo, response)

    def upload(self, msg_data: bytes):
        _, index, subindex = SDO_STRUCT.unpack(msg_data[:4])

        variable = self._lookup(index, subindex)

        if variable.access not in ('ro', 'rw', 'constant'):
            raise SDODomainAbort(0x06010001)  # read a write-only object

        value = self._node.object_dictionary.read(variable)
        value = int(value / variable.factor)

        dt_struct = struct_dict[variable.datatype]

        try:
            data = dt_struct.pack(value)
        except struct.error:
            raise SDODomainAbort(0x06090030)  # value range exceeded

        cmd = 0x43 + ((4 - dt_struct.size) << 2)

        response = SDO_STRUCT.pack(cmd, index, subindex) + data
        response += bytes(4 - dt_struct.size)

        self._node.adapter.send(self._cob_txsdo, response)
