from enum import IntEnum
import logging
from typing import TYPE_CHECKING

from durand.object_dictionary import Variable
from durand.datatypes import DatatypeEnum as DT

if TYPE_CHECKING:
    from ..node import Node


log = logging.getLogger(__name__)


class StateEnum(IntEnum):
  INITIALISATION = 0
  STOPPED = 4
  OPERATIONAL = 5
  PRE_OPERATIONAL = 127


class NMTService:
    def __init__(self, node: 'Node'):
        self._node = node
        self.state = None

        node.add_subscription(cob_id=0, callback=self.handle_msg)

        heartbeat_producer = Variable(0x1017, 0, DT.UNSIGNED16, 'rw')
        node.object_dictionary.add_update_callback(heartbeat_producer, self._update_heartbeat)
        node.object_dictionary.add_object(heartbeat_producer)

        self.set_state(StateEnum.INITIALISATION)

    def handle_msg(self, msg: bytes):
        cs, node_id = msg[:2]

        if node_id not in (0, self._node.node_id):  # 0 is used for broadcast
            return

        if cs == 0x01 and self.state in (StateEnum.PRE_OPERATIONAL, StateEnum.STOPPED):
            self.set_state(StateEnum.OPERATIONAL)  # start node
        elif cs == 0x02 and self.state in (StateEnum.PRE_OPERATIONAL, StateEnum.OPERATIONAL):
            self.set_state(StateEnum.STOPPED)  # stop node
        elif cs == 0x80 and self.state in (StateEnum.OPERATIONAL, StateEnum.STOPPED):
            self.set_state(StateEnum.PRE_OPERATIONAL)  # enter pre-operational
        elif cs == 0x81:
            self.set_state(StateEnum.INITIALISATION)  # Reset Node
        elif cs == 0x82:  # Reset Communication
            raise NotImplementedError('Reset Communication command (0x82) not implemented')
        else:
            log.error('Unknown NMT command specifier 0x%02X', cs)

    def set_state(self, state: StateEnum):
        if state == self.state:
            return

        if state == StateEnum.INITIALISATION:
            # send bootup message
            self._node.adapter.send(0x700 + self._node.node_id, b'\x00')
            state = StateEnum.PRE_OPERATIONAL  # continue with PRE_OPERATIONAL state

        # TODO Handle PRE_OPERATIONAL, OPERATIONAL and STOPPED

        self.state = state

    def _update_heartbeat(self, value: int):
        pass