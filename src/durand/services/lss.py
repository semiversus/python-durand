from typing import TYPE_CHECKING, List, Optional
from enum import IntEnum
import logging
import struct

from durand.scheduler import get_scheduler
from .nmt import StateEnum

if TYPE_CHECKING:
    from ..node import Node

log = logging.getLogger(__name__)


class LSSState(IntEnum):
    WAITING = 0
    CONFIGURATION = 1


def check_length(length: int):
    """ Decorator for cmd_ methods checking the expected packet length """
    def wrap(cmd_method):
        def wrapped_cmd(self, msg: bytes):
            if len(msg) == length:
                return cmd_method(self, msg)
            log.info('LSS got packet with wrong length {msg!r}, expected {length} bytes')
        return wrapped_cmd
    return wrap


class LSSSlave:
    def __init__(self, node: "Node"):
        self._node = node

        self._state = LSSState.WAITING

        self._received_selective_address: List[Optional[int]] = [None] * 4
        self._remote_responder_address: List[Optional[int]] = [None] * 6
        self._fastscan_state = 0

        self._pending_baudrate = None
        self._change_baudrate_cb = None

        node.network.add_subscription(cob_id=0x7E5, callback=self.handle_msg)
        node.nmt.state_callbacks.add(self.on_nmt_state_update)

    def set_baudrate_change_callback(self, cb):
        self._change_baudrate_cb = cb

    def on_nmt_state_update(self, state: StateEnum):
        if state == StateEnum.INITIALISATION:
            self._state = LSSState.WAITING
            self._received_selective_address = [None] * 4

    def _get_own_address(self):
        lss_address = [None] * 4

        for index in range(4):
            lss_address[index] = self._node.object_dictionary.read(0x1018, index + 1)

        return lss_address

    def handle_msg(self, _cob_id: int, msg: bytes):
        if len(msg) < 1:
            log.info(f'LSS got packet with wrong length {msg!r}')
            return

        cs = msg[0]

        if self._state == LSSState.WAITING:
            method = LSSSlave._waiting_cs_dict.get(cs, None)
        else:
            method = LSSSlave._configuration_cs_dict.get(cs, None)

        if method is None:
            return

        method(self, msg)

    @check_length(2)
    def cmd_switch_mode_global_configuration(self, msg: bytes):
        if msg[1] != 1:  # check if requested mode is CONFIGURATION
            return

        self._state = LSSState.CONFIGURATION

    @check_length(2)
    def cmd_switch_mode_global_waiting(self, msg: bytes):
        if msg[1] != 0:  # check if requested mode is WAITING
            return

        if self._node.node_id == 0xFF and self._node.nmt.pending_node_id != 0xFF:
            self._node.nmt.reset()

        self._state = LSSState.WAITING

    @check_length(6)
    def cmd_switch_mode_selective(self, msg: bytes):
        index = msg[0] - 0x40

        self._received_selective_address[index] = int.from_bytes(
            msg[1:5], "little", signed=False
        )

        if None in self._received_selective_address:
            return

        if self._received_selective_address == self._get_own_address():
            self._state = LSSState.CONFIGURATION
            self._node.network.send(0x7E4, b"\x44" + bytes(7))

        self._received_selective_address = [None] * 4

    @check_length(1)
    def cmd_inquire_identity(self, msg: bytes):
        index = msg[0] - 0x5A
        value = self._get_own_address()[index]
        self._node.network.send(0x7E4, msg[:1] + value.to_bytes(4, "little") + bytes(3))

    @check_length(1)
    def cmd_inquire_node_id(self, _msg: bytes):
        self._node.network.send(
            0x7E4, b"\x5e" + self._node.node_id.to_bytes(1, "little") + bytes(6)
        )

    @check_length(2)
    def cmd_configure_node_id(self, msg: bytes):
        node_id = msg[1]

        if 1 <= node_id <= 127 or node_id == 0xFF:
            self._node.nmt.pending_node_id = node_id
            result = 0
        else:
            result = 1

        self._node.network.send(
            0x7E4, b"\x11" + result.to_bytes(1, "little") + bytes(6)
        )

    @check_length(4)
    def cmd_configure_bit_timing(self, msg: bytes):
        valid_table_entries = (0, 1, 2, 3, 4, 6, 7, 8)
        selector, index = msg[1:3]

        if (
            selector != 0
            or index not in valid_table_entries
            or self._change_baudrate_cb is None
        ):
            self._node.network.send(0x7E4, b"\x13\x01" + bytes(6))
            return

        self._pending_baudrate = index
        self._node.network.send(0x7E4, b"\x13\x00" + bytes(6))

    @check_length(4)
    def cmd_activate_bit_timing(self, msg: bytes):
        delay = int.from_bytes(msg[1:3], "little") / 1000  # [seconds]

        if self._pending_baudrate is not None:
            get_scheduler().add(delay, self._change_baudrate, args=(delay,))

    def _change_baudrate(self, delay: float):
        if self._change_baudrate_cb:
            self._change_baudrate_cb(self._pending_baudrate)
        self._pending_baudrate = None
        get_scheduler().add(delay, self._node.nmt.reset)

    @check_length(1)
    def cmd_store_configuration(self, _msg: bytes):
        # store configuration is not supported
        self._node.network.send(0x7E4, b"\x17\x01" + bytes(6))

    @check_length(6)
    def cmd_identify_remote_responders(self, msg: bytes):
        index = msg[0] - 0x46
        value = int.from_bytes(msg[1:5], "little")
        self._remote_responder_address[index] = value

        if None in self._remote_responder_address:
            return

        vendor, product, revision, serial = self._get_own_address()

        if (
            vendor == self._remote_responder_address[0]
            and product == self._remote_responder_address[1]
            and self._remote_responder_address[2]
            <= revision
            <= self._remote_responder_address[3]
            and self._remote_responder_address[4] <= serial <= self._remote_responder_address[5]
        ):

            self._node.network.send(0x7E4, b"\x47" + bytes(7))

        self._remote_responder_address = [None] * 6

    @check_length(1)
    def cmd_identify_nonconfigured_remote_responders(self, _msg: bytes):
        if self._node.node_id == 0xFF:
            self._node.network.send(0x7E4, b"\x50" + bytes(7))

    @check_length(5)
    def cmd_fastscan(self, msg: bytes):
        if self._node.node_id != 0xFF:
            return

        id_number, bit_checked, lss_sub, lss_next = struct.unpack("IBBB", msg[1:])

        if bit_checked == 0x80:
            self._fastscan_state = 0
            self._node.network.send(0x7E4, b"\x4F" + bytes(7))
            return

        if lss_sub != self._fastscan_state:
            return

        mask = ~((1 << bit_checked) - 1)
        lss_address = self._get_own_address()

        if (lss_address[lss_sub] & mask) != (id_number & mask):
            return

        self._fastscan_state = lss_next

        if bit_checked == 0 and lss_sub == 3:
            self._state = LSSState.CONFIGURATION

        self._node.network.send(0x7E4, b"\x4F" + bytes(7))

    _waiting_cs_dict = {
        0x04: cmd_switch_mode_global_configuration,
        0x40: cmd_switch_mode_selective,
        0x41: cmd_switch_mode_selective,
        0x42: cmd_switch_mode_selective,
        0x43: cmd_switch_mode_selective,
        0x46: cmd_identify_remote_responders,
        0x47: cmd_identify_remote_responders,
        0x48: cmd_identify_remote_responders,
        0x49: cmd_identify_remote_responders,
        0x4A: cmd_identify_remote_responders,
        0x4B: cmd_identify_remote_responders,
        0x4C: cmd_identify_nonconfigured_remote_responders,
        0x51: cmd_fastscan,
    }

    _configuration_cs_dict = {
        0x04: cmd_switch_mode_global_waiting,
        0x11: cmd_configure_node_id,
        0x13: cmd_configure_bit_timing,
        0x15: cmd_activate_bit_timing,
        0x17: cmd_store_configuration,
        0x46: cmd_identify_remote_responders,
        0x47: cmd_identify_remote_responders,
        0x48: cmd_identify_remote_responders,
        0x49: cmd_identify_remote_responders,
        0x4A: cmd_identify_remote_responders,
        0x4B: cmd_identify_remote_responders,
        0x4C: cmd_identify_nonconfigured_remote_responders,
        0x51: cmd_fastscan,
        0x5A: cmd_inquire_identity,
        0x5B: cmd_inquire_identity,
        0x5C: cmd_inquire_identity,
        0x5D: cmd_inquire_identity,
        0x5E: cmd_inquire_node_id,
    }
