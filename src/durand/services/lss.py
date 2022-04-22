from typing import TYPE_CHECKING
from enum import IntEnum
import logging

from .nmt import StateEnum
from durand.scheduler import get_scheduler

if TYPE_CHECKING:
    from ..node import Node

log = logging.getLogger(__name__)


class LSSState(IntEnum):
    WAITING = 0
    CONFIGURATION = 1


class LSS:
    def __init__(self, node: "Node"):
        self._node = node

        self._state = LSSState.WAITING

        self._received_address = [None] * 4

        self._pending_baudrate = None
        self._change_baudrate_cb = None

        node.adapter.add_subscription(cob_id=0x7e5, callback=self.handle_msg)
        node.nmt.state_callbacks.add(self.on_nmt_state_update)

    def set_baudrate_change_callback(self, cb):
        self._change_baudrate_cb = cb

    def on_nmt_state_update(self, state: StateEnum):
        if state == StateEnum.INITIALISATION:
            self._state = LSSState.WAITING
            self._received_address = [None] * 4

    def _get_own_address(self):
        lss_address = [None] * 4

        for index in range(4):
            var = self._node.object_dictionary.lookup(0x1018, index + 1)
            lss_address[index] = self._node.object_dictionary.read(var)

        return lss_address

    def handle_msg(self, cob_id: int, msg: bytes):
        cs = msg[0]

        if self._state == LSSState.WAITING:
            if cs not in (0x04, 0x40, 0x41, 0x42, 0x43):
                return
        elif cs not in (0x04, 0x11, 0x13, 0x15, 0x17, 0x5a, 0x5b, 0x5c, 0x5d, 0x5e):
                return

        if cs == 0x04:  # switch state global
            mode = msg[1]
            if mode not in (0, 1):
                return

            if self._state == mode:
                return

            if mode == LSSState.WAITING and self._node.node_id == 0xFF and self._node.nmt.pending_node_id != 0xFF:
                self._node.nmt.reset()

            self._state = mode
        elif cs in (0x40, 0x41, 0x42, 0x43):  # select vendor id, product code, revision number, serial number
            self._received_address[cs - 0x40] = int.from_bytes(msg[1:5], 'little', signed=False)

            if cs != 0x43:
                # TODO: should it only check on serial number or as soon as it matches?
                return

            if (None in self._received_address):
                return

            if self._received_address == self._get_own_address():
                self._state = LSSState.CONFIGURATION
                self._node.adapter.send(0x7e4, b"\x44" + bytes(7))
        elif cs in (0x5a, 0x5b, 0x5c, 0x5d):  # inquire vendor id, product code, revision number, serial number
            value = self._get_own_address()[cs - 0x5a]
            self._node.adapter.send(0x7e4, msg[:1] + value.to_bytes(4, 'little') + bytes(3))
        elif cs == 0x5e:  # inquire node id
            self._node.adapter.send(0x7e4, b"\x5e" + self._node.node_id.to_bytes(1, 'little') + bytes(6))
        elif cs == 0x11:  # set node id
            node_id = msg[1]

            if 1 <= node_id <= 127 or node_id == 0xff:
                self._node.nmt.set_pending_node_id(msg[1])
                result = 0
            else:
                result = 1

            self._node.adapter.send(0x7e4, b"\x11" + result.to_bytes(1, 'little') + bytes(6))
        elif cs == 0x13:  # configure bit timing
            if msg[1] != 0 or msg[2] in (0, 1, 2, 3, 4, 6, 7, 8) or self._change_baudrate_cb is None:
                self._node.adapter.send(0x7e4, b"\x13\x01" + bytes(6))
                return

            self._pending_baudrate = msg[2]
            self._node.adapter.send(0x7e4, b"\x13\x00" + bytes(6))
        elif cs == 0x15:  # activate bit timing
            delay = int.from_bytes(msg[1:3], 'little') / 1000  # [seconds]
            if self._pending_baudrate is not None:
                get_scheduler().add(delay, self._change_baudrate, args=(delay,))
        elif cs == 0x17:  # store configuration
            # store configuration is not supported
            self._node.adapter.send(0x7e4, b"\x17\x01" + bytes(6))

    def _change_baudrate(self, delay: float):
        self._change_baudrate_cb(self._pending_baudrate)
        self._pending_baudrate = None
        get_scheduler().add(delay, self._node.nmt.reset)
