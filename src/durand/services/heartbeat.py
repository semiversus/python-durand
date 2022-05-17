from typing import TYPE_CHECKING

from durand.object_dictionary import Variable
from durand.datatypes import DatatypeEnum as DT
from durand.scheduler import get_scheduler

if TYPE_CHECKING:
    from durand.node import Node


class HeartbeatProducer:
    def __init__(self, node: "Node"):
        self._handle = None
        self._node = node

        node.object_dictionary[0x1017] = Variable(
            DT.UNSIGNED16, "rw", name="Producer Heartbeat Time"
        )
        node.object_dictionary.update_callbacks[(0x1017, 0)].add(self._update_interval)

    def _update_interval(self, value: int):
        sched = get_scheduler()

        if self._handle:
            sched.cancel(self._handle)
            self._handle = None

        if value:
            self._process_heartbeat(value / 1000)

    def _process_heartbeat(self, interval: float):
        msg = bytes((self._node.nmt.state,))  # data contains NMT state
        self._node.adapter.send(0x700 + self._node.node_id, msg)

        self._handle = get_scheduler().add(
            interval, self._process_heartbeat, args=(interval,)
        )
