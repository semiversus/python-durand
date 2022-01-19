from typing import TYPE_CHECKING
import struct
import logging

from durand.datatypes import struct_dict
from durand.object_dictionary import Variable

if TYPE_CHECKING:
    from durand.node import Node


log = logging.getLogger(__name__)


class TPDO:
    def __init__(self, node: 'Node', index: int):
        self._node = node
        self._objects = ()
        self._cob_id = 0x180 + (index - 1) * 0x100 + node.node_id

        #heartbeat_producer = Variable(0x1017, 0, DT.UNSIGNED16, 'rw')

        #node.object_dictionary.add_object(heartbeat_producer)
        #node.object_dictionary.add_update_callback(heartbeat_producer, self._update_interval)

    def map_objects(self, *variables: Variable):
        for variable in self._objects:
            self._node.object_dictionary.remove_update_callback(variable, self._on_change)

        for variable in variables:
            self._node.object_dictionary.add_update_callback(variable, self._on_change)

        self._objects = variables

    def _on_change(self, _value):
        self._transmit()

    def _transmit(self):
        msg = b''
        for variable in self._objects:
            value = self._node.object_dictionary.read(variable)
            value = int(value / variable.factor)

            dt_struct = struct_dict[variable.datatype]

            try:
                msg += dt_struct.pack(value)
            except struct.error:
                log.error(f'Variable {variable!r} could not pack value {value!r}')
                return
        self._node.adapter.send(self._cob_id, msg)


class RPDO:
    def __init__(self, node: 'Node', index: int):
        pass
