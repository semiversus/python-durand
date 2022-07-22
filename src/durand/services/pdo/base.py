""" TPDO and RPDO have a lot in common. This module defiens a base class for RPDO and TPDO
"""
from abc import abstractmethod
from typing import TYPE_CHECKING, Sequence

from durand.object_dictionary import TMultiplexor, Variable
from durand.services.nmt import StateEnum

if TYPE_CHECKING:
    from durand.node import Node


class PDOBase:
    COB_OFFSET = 0
    MAPPING_ARRAY_INDEX = 0

    def __init__(self, node: "Node", index: int):
        self._node = node
        self._index = index
        self._cob_id = 0

        self._transmission_type = 255

        self._multiplexors: Sequence[TMultiplexor] = ()

    @property
    def node(self):
        return self._node

    def _update_nmt_state(self, state: StateEnum):
        if state == StateEnum.OPERATIONAL:
            if self._index < 4:
                self._cob_id = (
                    (self._cob_id & 0xE000_0000)
                    + self.COB_OFFSET
                    + (self._index * 0x100)
                    + self._node.node_id
                )

            self._activate_mapping()
        else:
            self._deactivate_mapping()

    def _downloaded_cob_id(self, value: int):
        self._cob_id = value
        # TODO: check RTR flag to be cleared

        if value & (1 << 31):
            self._deactivate_mapping()
        else:
            self._activate_mapping()

    def _downloaded_transmission_type(self, value: int):
        self.transmission_type = value

    @property
    def transmission_type(self):
        return self._transmission_type

    @transmission_type.setter
    def transmission_type(self, value: int):
        self._set_transmission_type(value)

    @abstractmethod
    def _set_transmission_type(self, value: int):
        """routine to set new transmission type"""

    @property
    def enable(self) -> bool:
        return not self._cob_id & (1 << 31)

    @enable.setter
    def enable(self, value: bool):
        if value:
            self._cob_id &= ~(1 << 31)
            self._activate_mapping()
        else:
            self._cob_id |= 1 << 31
            self._deactivate_mapping()

        self._update_od_cob_id()

    @abstractmethod
    def _update_od_cob_id(self):
        """write self._cob_id to object dictionary"""

    def _downloaded_map_length(self, length):
        multiplexors = []

        for subindex in range(1, length + 1):
            value = self._node.object_dictionary.read(
                self.MAPPING_ARRAY_INDEX + self._index, subindex
            )
            index, subindex = value >> 16, (value >> 8) & 0xFF
            multiplexors.append((index, subindex))

        self._map(multiplexors)

    @property
    def mapping(self):
        return self._multiplexors

    @mapping.setter
    def mapping(self, multiplexors: Sequence[TMultiplexor]):
        self._map(multiplexors)
        self._node.object_dictionary.write(
            self.MAPPING_ARRAY_INDEX + self._index, 0, len(multiplexors)
        )
        for _entry, multiplexor in enumerate(multiplexors):
            index, subindex = multiplexor
            variable = self._node.object_dictionary.lookup(index, subindex)
            assert isinstance(variable, Variable), "Variable expected"
            # TODO: check if variable.size is None
            # TODO: check if overall size <= 8
            assert variable.size is not None
            value = (index << 16) + (subindex << 8) + (variable.size * 8)
            self._node.object_dictionary.write(
                self.MAPPING_ARRAY_INDEX + self._index, _entry + 1, value
            )

    def _map(self, multiplexors: Sequence[TMultiplexor]):
        self._deactivate_mapping()
        self._multiplexors = tuple(multiplexors)
        self._activate_mapping()

    @abstractmethod
    def _activate_mapping(self):
        """Activate the new mapping"""

    @abstractmethod
    def _deactivate_mapping(self):
        """Dectivate the current mapping"""

    def _validate_state(self) -> bool:
        if self._cob_id & (1 << 31) or not self._multiplexors:
            return False

        if self._node.nmt.state != StateEnum.OPERATIONAL:
            return False

        return True
