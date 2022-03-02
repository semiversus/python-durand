import struct
from enum import Enum
from typing import TYPE_CHECKING
import logging

from durand.datatypes import DatatypeEnum as DT
from durand.datatypes import is_numeric
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


TransferDirection = Enum('TransferDirection', 'UPLOAD DOWNLOAD UPLOAD_BLOCK DOWNLOAD_BLOCK')


class TransferState:
    def __init__(self, variable: Variable, direction: TransferDirection):
        self.variable = variable
        self.direction = direction
        self.manager = None

        self.buffer = bytearray()

        # used for block transfer
        self.sequence_number = None
        self.use_crc = None

        # used for segmented transfer
        self.toggle_bit = False


class BaseDownloadManager:
    def on_receive(self, data: bytes):
        """ on_received is called when new data is received

        :param data: bytes received and to be appended
        """

    def on_finish(self):
        """ on_finish is called when the transfer is successfully completed
        """

    def on_abort(self):
        """ on_abort is called when the transfer was aborted
        """


def parse_data(variable: Variable, data: bytes):
    try:
        value = variable.unpack(data)
    except struct.error:
        raise SDODomainAbort(0x06070010, variable)  # datatype size is not matching

    if variable.minimum is not None and value < variable.minimum:
        raise SDODomainAbort(0x06090032, variable)  # value too low

    if variable.maximum is not None and value > variable.maximum:
        raise SDODomainAbort(0x06090031, variable)  # value too high

    return value


class SDOServer:
    def __init__(self, node: 'Node', index=0, cob_rx: int=None, cob_tx: int=None):
        self._node = node
        self._transfer_state = None

        self.download_callback = None

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
            elif self._transfer_state and self._transfer_state.direction in (
                TransferDirection.DOWNLOAD_BLOCK, TransferDirection.UPLOAD_BLOCK):
                if self._transfer_state.direction == TransferDirection.DOWNLOAD_BLOCK:
                    self.download_sub_block(msg)
                else:
                    self.upload_sub_block(msg)
            elif ccs == 0:  # download segment
                self.download_segment(msg)
            elif ccs == 1:  # init download
                self.init_download(msg)
            elif ccs == 2:  # init upload
                self.init_upload(msg)
            elif ccs == 6:  # init/end download block
                if msg[0] & 0x01:  # end block transfer
                    self.download_block_end(msg)
                else:  # init block transfer
                    self.download_block_init(msg)
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

        variable = self._lookup(index, subindex)

        if variable.access not in ('rw', 'wo'):
            raise SDODomainAbort(0x06010002)  # write a read-only object

        response = SDO_STRUCT.pack(0x60, index, subindex) + bytes(4)

        if not cmd & 0x02:  # segmented transfer (not expitited)
            if cmd & 0x01:  # size specified
                size = int.from_bytes(msg[4:], 'little')
            else:
                size = None

            self._transfer_state = TransferState(variable, TransferDirection.DOWNLOAD)

            if self.download_callback:
                self._transfer_state.manager = self.download_callback(self._node, variable, size)

            self._node.adapter.send(self._cob_tx, response)
            return

        if cmd & 0x01:  # size specified
            size = 4 - ((cmd >> 2) & 0x03)
        else:
            size = variable.size

        value = parse_data(variable, msg[4: 4 + size])

        try:
            self._node.object_dictionary.write(variable, value)
        except Exception:
            raise SDODomainAbort(0x08000020)  # data can't be stored

        self._node.adapter.send(self._cob_tx, response)

    def download_segment(self, msg: bytes):
        if self._transfer_state is None or self._transfer_state.direction != TransferDirection.DOWNLOAD:
            raise SDODomainAbort(0x05040001, variable=False)  # client command specificer not valid

        toggle_bit = bool(msg[0] & 0x10)

        if toggle_bit != self._transfer_state.toggle_bit:
            variable = self._transfer_state.variable
            self._transfer_state = None
            raise SDODomainAbort(0x05030000, variable)  # toggle bit not altered

        self._transfer_state.toggle_bit = not self._transfer_state.toggle_bit

        size = 7 - ((msg[0] & 0x0E) >> 1)
        data = msg[1: 1 + size]

        if self._transfer_state.manager:
            self._transfer_state.manager.on_receive(data)
        else:
            self._transfer_state.buffer.extend(data)

        if msg[0] & 0x01:  # check continue bit
            try:
                if self._transfer_state.manager:
                    self._transfer_state.manager.on_finish()
                else:
                    value = parse_data(self._transfer_state.variable, self._transfer_state.buffer)
                    self._node.object_dictionary.write(self._transfer_state.variable, value)
            except SDODomainAbort as e:
                raise e
            except Exception as e:
                raise SDODomainAbort(0x08000020, self._transfer_state.variable)  # data can't be stored
            finally:
                self._transfer_state.buffer.clear()
                self._transfer_state = None

        cmd = 0x20 + (toggle_bit << 4)
        self._node.adapter.send(self._cob_tx, cmd.to_bytes(1, 'little') + bytes(7))

    def download_block_init(self, msg: bytes):
        cmd, index, subindex = SDO_STRUCT.unpack(msg[:4])

        variable = self._lookup(index, subindex)

        if variable.access not in ('rw', 'wo'):
            raise SDODomainAbort(0x06010002)  # write a read-only object

        self._transfer_state = TransferState(variable, TransferDirection.DOWNLOAD_BLOCK)
        
        self._transfer_state.use_crc = bool(cmd & 0x04)

        if cmd & 0x02:  # size bit
            size = struct.unpack('<I', msg[4:])
        else:
            size = None
        
        self._transfer_state.sequence_number = 0

        cmd = 0xA4
        self._node.adapter.send(self._cob_tx, cmd.to_bytes(1, 'little') + msg[1: 4] + b'\x7F' + bytes(3))

    def download_sub_block(self, msg: bytes):
        pass
        
    def init_upload(self, msg_data: bytes):
        _, index, subindex = SDO_STRUCT.unpack(msg_data[:4])

        variable = self._lookup(index, subindex)

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
        _, *multiplexor = SDO_STRUCT.unpack(msg_data[:4])

        if self._transfer_state and self._transfer_state.variable.multiplexor == tuple(multiplexor):
            if self._transfer_state.manager:
                self._transfer_state.manager.on_abort()
            self._transfer_state.buffer.clear()
            self._transfer_state = None
            return
