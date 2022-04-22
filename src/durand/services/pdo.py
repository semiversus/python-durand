from typing import TYPE_CHECKING
import struct
import logging

from durand.object_dictionary import Variable

if TYPE_CHECKING:
    from durand.node import Node


log = logging.getLogger(__name__)


class TPDO:
    def __init__(self, node: "Node", index: int):
        self._node = node
        self._cob_id = 0x180 + (index - 1) * 0x100
        self._objects = ()

    def map_objects(self, *variables: Variable):
        for variable in self._objects:
            self._node.object_dictionary.update_callbacks[variable].remove(
                self._on_change
            )

        for variable in variables:
            self._node.object_dictionary.update_callbacks[variable].add(self._on_change)

        self._objects = variables

    def _on_change(self, _value):
        self._transmit()

    def _transmit(self):
        msg = b""
        for variable in self._objects:
            value = self._node.object_dictionary.read(variable)

            try:
                msg += variable.pack(value)
            except struct.error:
                log.error(f"Variable {variable!r} could not pack value {value!r}")
                return
        self._node.adapter.send(self._cob_id + self._node.node_id, msg)


class RPDO:
    def __init__(self, node: "Node", index: int):
        self._node = node

        cob_id = 0x200 + (index - 1) * 0x100 + node.node_id
        node.adapter.add_subscription(cob_id=cob_id, callback=self.handle_msg)

        self._objects = ()

    def map_objects(self, *variables: Variable):
        self._objects = variables

    def handle_msg(self, cob_id: int, msg: bytes):
        for variable in self._objects:
            value = variable.unpack(msg[: variable.size])
            self._node.object_dictionary.write(variable, value)
            msg = msg[variable.size :]
