from typing import TYPE_CHECKING
import struct
import logging

from durand.object_dictionary import Variable, Record
from durand.datatypes import DatatypeEnum as DT

if TYPE_CHECKING:
    from durand.node import Node


log = logging.getLogger(__name__)


class TPDO:
    def __init__(self, node: "Node", index: int):
        self._node = node

        if index < 4:
            self._cob_id = 0x8000_0180 + index * 0x100
        else:
            self._cob_id = 0x80000000

        self._transmission_type = 254
        self._objects = ()


        od = self._node.object_dictionary

        tpdo_record = Record()
        tpdo_record[1] = Variable(DT.UNSIGNED32, "rw", self._cob_id)  # cob id used by tpdo
        tpdo_record[2] = Variable(DT.UNSIGNED8, "rw", self._transmission_type)
        tpdo_record[3] = Variable(DT.UNSIGNED16, "rw", 0)  # inhibit time [µs]
        tpdo_record[4] = Variable(DT.UNSIGNED16, "rw", 0)  # event timer [ms]
        tpdo_record[5] = Variable(DT.UNSIGNED16, "rw", 0)  # sync start value
        tpdo_record.add_largest_subindex()

        od[0x1800 + index] = tpdo_record

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
