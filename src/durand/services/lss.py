from typing import TYPE_CHECKING
from enum import IntEnum
import logging

from .nmt import StateEnum

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

        node.adapter.add_subscription(cob_id=0x7e5, callback=self.handle_msg)
        node.nmt.state_callbacks.add(self.on_nmt_state_update)

    def on_nmt_state_update(self, state: StateEnum):
        if state == StateEnum.INITIALISATION:
            self._state = LSSState.WAITING
            self._received_address = [None] * 4
    
    def get_own_address(self):
        lss_address = [None] * 4

        for index in range(4):
            var = self._node.object_dictionary.lookup(0x1018, index + 1)
            lss_address[index] = self._node.object_dictionary.read(var)
        
        return lss_address

    def handle_msg(self, cob_id: int, msg: bytes):
        cs = msg[0]

        if cs in (0x40, 0x41, 0x42, 0x43):  # vendor id, product code, revision number, serial number
            self._received_address[cs - 0x40] = int.from_bytes(msg[1:5], 'little', signed=False)
            
            if cs != 0x43:
                # TODO: should it only check on serial number or as soon as it matches?
                return

            if (None in self._received_address):
                return

            if self._received_address == self.get_own_address():
                self._state = LSSState.CONFIGURATION
                self._node.adapter.send(0x7e4, b"\x44" + bytes(7))
        elif cs == 0x5e and self._state == LSSState.CONFIGURATION:  # inquire node id
            self._node.adapter.send(0x7e4, b"\x5e" + self._node.node_id.to_bytes(1, 'little') + bytes(6))
        elif cs == 0x11 and self._state == LSSState.CONFIGURATION:  # set node id
            node_id = msg[1]
            
            if 1 <= node_id <= 127 or node_id == 0xff:
                self._node.nmt.set_pending_node_id(msg[1])
                result = 0
            else:
                result = 1

            self._node.adapter.send(0x7e4, b"\x11" + result.to_bytes(1, 'little') + bytes(6))
            