from enum import IntEnum
import logging
from typing import TYPE_CHECKING

from ..callback_handler import CallbackHandler

if TYPE_CHECKING:
    from ..node import Node


log = logging.getLogger(__name__)


class StateEnum(IntEnum):
    INITIALISATION = 0
    STOPPED = 4
    OPERATIONAL = 5
    PRE_OPERATIONAL = 127


class NMTService:
    def __init__(self, node: "Node"):
        self._node = node
        self.pending_node_id = node.node_id

        self.state_callbacks = CallbackHandler()

        self.state = None

        node.adapter.add_subscription(cob_id=0, callback=self.handle_msg)

        self.set_state(StateEnum.INITIALISATION)

    def handle_msg(self, cob_id: int, msg: bytes):
        cs, node_id = msg[:2]

        if node_id not in (0, self._node.node_id):  # 0 is used for broadcast
            return

        if cs == 0x01:  # start node
            self.set_state(StateEnum.OPERATIONAL)
        elif cs == 0x02:  # stop node
            self.set_state(StateEnum.STOPPED)
        elif cs == 0x80:  # enter pre-operational
            self.set_state(StateEnum.PRE_OPERATIONAL)
        elif cs in (0x81, 0x82):  # Reset Node or Reset Communication
            self.set_state(StateEnum.INITIALISATION)
            self.set_state(StateEnum.PRE_OPERATIONAL)
        else:
            log.error("Unknown NMT command specifier 0x%02X", cs)

    def reset(self):
        self.set_state(StateEnum.INITIALISATION)
        self.set_state(StateEnum.PRE_OPERATIONAL)

    def set_state(self, state: StateEnum):
        if state == self.state:
            return

        if state == StateEnum.INITIALISATION:
            self._node.node_id = self.pending_node_id

            # send bootup message
            self._node.adapter.send(0x700 + self._node.node_id, b"\x00")

        self.state = state

        self.state_callbacks.call(state)
