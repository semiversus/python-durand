from typing import TYPE_CHECKING
import logging

from durand.object_dictionary import TMultiplexor, Variable, Record, Array
from durand.datatypes import DatatypeEnum as DT
from durand.services.nmt import StateEnum

if TYPE_CHECKING:
    from durand.node import Node


log = logging.getLogger(__name__)


class TPDO:
    def __init__(self, node: "Node", index: int):
        self._node = node
        self._index = index

        if index < 4:
            self._cob_id = 0x8000_0180 + (index * 0x100) + node.node_id
        else:
            self._cob_id = 0x8000_0000

        self._transmission_type = 254

        self._multiplexors = ()
        self._pack_functions = None
        self._cache = None

        od = self._node.object_dictionary

        param_record = Record()
        access = "ro" if index < 4 else "rw"
        param_record[1] = Variable(DT.UNSIGNED32, access, self._cob_id)  # used cob id
        param_record[2] = Variable(DT.UNSIGNED8, "rw", self._transmission_type)
        od[0x1800 + index] = param_record

        od.download_callbacks[(0x1A00 + index, 1)].add(self._downloaded_cob_id)

        map_array = Array(Variable(DT.UNSIGNED32, "rw"), length=8)
        od[0x1A00 + index] = map_array

        od.write(0x1A00 + index, 0, 0)  # set number of mapped objects to 0
        od.download_callbacks[(0x1A00 + index, 0)].add(self._downloaded_map_length)

        node.nmt.state_callbacks.add(self._update_nmt_state)

    def _update_nmt_state(self, state: StateEnum):
        if state == StateEnum.OPERATIONAL:
            if self._index < 4:
                self._cob_id = (self._cob_id & 0xE000_000) + (self._index * 0x100) + self._node.node_id
                
            self._activate_mapping()
        else:
            self._deactivate_mapping()

    def _downloaded_cob_id(self, value: int):
        self._cob_id = (self._cob_id & 0xE000_0000) + (value & 0x1FFF_FFFF)

        if value & (1 << 31):
            self.disable()
        else:
            self.enable()

    def enable(self):
        self._cob_id &= ~(1 << 31)
        self._activate_mapping()

    def disable(self):
        self._cob_id |= 1 << 31
        self._deactivate_mapping()

    def _downloaded_map_length(self, length):
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
        self._deactivate_mapping()
        self._multiplexors = multiplexors
        self._activate_mapping()
        
    def _deactivate_mapping(self):
        if self._cache is None:  # check if already deactivated
            return

        update_callbacks = self._node.object_dictionary.update_callbacks

        for multiplexor, function in zip(self._multiplexors, self._pack_functions):
            update_callbacks[multiplexor].remove(function)

        self._cache = None
        self._pack_functions = None

    def _activate_mapping(self):
        if self._cache is not None:  # check if already activated
            return
        
        if not self._cob_id & (1 << 31) or not self._multiplexors:
            return
        
        if self._node.nmt.state != StateEnum.OPERATIONAL:
            return
        
        self._pack_functions = []
        self._cache = []

        update_callbacks = self._node.object_dictionary.update_callbacks

        for index, multiplexor in enumerate(self._multiplexors):
            variable = self._node.object_dictionary.lookup(*multiplexor)
            
            def pack(value, index=index, variable=variable):
                self._cache[index] = variable.pack(value)
                if self._transmission_type in (254, 255):
                    self._transmit()

            value = self._node.object_dictionary.read(*multiplexor)
            self._cache.append(variable.pack(value))
            self._pack_functions.append(pack)
            update_callbacks[multiplexor].add(pack)

    def _transmit(self):
        data = b"".join(self._cache)
        self._node.adapter.send(self._cob_id & 0x1FFF_FFFF, data)

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
