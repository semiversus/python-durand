from audioop import mul
from typing import TYPE_CHECKING
from functools import partial
import struct
import logging

from durand.object_dictionary import TMultiplexor, Variable, Record, Array
from durand.datatypes import DatatypeEnum as DT

if TYPE_CHECKING:
    from durand.node import Node


log = logging.getLogger(__name__)


class TPDO:
    def __init__(self, node: "Node", index: int):
        self._node = node
        self._index = index

        if index < 4:
            self._cob_id = 0x8000_0180 + index * 0x100
        else:
            self._cob_id = 0x80000000

        self._transmission_type = 254
        self._objects = ()

        od = self._node.object_dictionary

        param_record = Record()
        param_record[1] = Variable(DT.UNSIGNED32, "rw", self._cob_id)  # used cob id
        param_record[2] = Variable(DT.UNSIGNED8, "rw", self._transmission_type)
        od[0x1800 + index] = param_record

        od.download_callbacks[(0x1A00 + index, 1)].add(self._update_cob_id)

        map_array = Array(Variable(DT.UNSIGNED32, "rw"), length=8)
        od[0x1A00 + index] = map_array

        od.write(0x1A00 + index, 0, 0)  # set number of mapped objects to 0
        od.download_callbacks[(0x1A00 + index, 0)].add(self._update_map_length)

    def _update_cob_id(self, value: int):
        self._cob_id = (self._cob_id & 0xE000_0000) + (value & 0x1FFF_FFFF)

        if value & (1 << 31):
            self.disable()
        else:
            self.enable()

    def enable(self):
        self._cob_id &= ~(1 << 31)

    def disable(self):
        self._cob_id |= 1 << 31

    def _update_map_length(self, length):
        multiplexors = list()

        for subindex in range(1, length + 1):
            value = self._node.object_dictionary.read(0x1A00 + index, subindex)
            index, subindex = value >> 16, (value >> 8) & 0xFF
            multiplexors.append((index, subindex))

        self._map(*multiplexors)

    def map(self, *multiplexors: TMultiplexor):
        self._map(*multiplexors)
        self._node.object_dictionary.write(0x1A00 + self._index, 0, len(multiplexors), downloaded=False)
        for _entry, multiplexor in enumerate(multiplexors):
            index, subindex = multiplexor
            variable = self._node.object_dictionary.lookup(index, subindex)
            value = (index << 16) + (subindex << 8) + variable.size
            self._node.object_dictionary.write(0x1A00 + self._index, _entry + 1, value, downloaded=False)

    def _map(self, *multiplexors: TMultiplexor):
        for multiplexor in self._objects:
            self._node.object_dictionary.update_callbacks[multiplexor].remove(
                self._on_change
            )

        for multiplexor in multiplexors:
            self._node.object_dictionary.update_callbacks[multiplexor].add(self._on_change)

        self._objects = multiplexors

    def _on_change(self, _value):
        self._transmit()

    def _transmit(self):
        msg = b""
        for multiplexor in self._objects:
            value = self._node.object_dictionary.read(*multiplexor)

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
