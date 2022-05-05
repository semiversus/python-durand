from typing import TYPE_CHECKING

from durand.object_dictionary import Variable

if TYPE_CHECKING:
    from durand.node import Node


class RPDO:
    def __init__(self, node: "Node", index: int):
        self._node = node

        cob_id = 0x200 + index * 0x100 + node.node_id
        node.adapter.add_subscription(cob_id=cob_id, callback=self.handle_msg)

        self._objects = ()

    def map_objects(self, *variables: Variable):
        self._objects = variables

    def handle_msg(self, cob_id: int, msg: bytes):
        for variable in self._objects:
            value = variable.unpack(msg[: variable.size])
            self._node.object_dictionary.write(variable, value)
            msg = msg[variable.size :]
