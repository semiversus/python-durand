from typing import TYPE_CHECKING

from durand.object_dictionary import TMultiplexor, Variable, Record, Array
from durand.datatypes import DatatypeEnum as DT
from durand.services.nmt import StateEnum


if TYPE_CHECKING:
    from durand.node import Node


class RPDO:
    def __init__(self, node: "Node", index: int):
        self._node = node
        self._index = index

        if index < 4:
            self._cob_id = 0x0000_0200 + (index * 0x100) + node.node_id
        else:
            self._cob_id = 0x8000_0000

        self._transmission_type = 255

        self._multiplexors = ()
        self._unpack_function = None

        self._synced_msg = None

        od = self._node.object_dictionary

        param_record = Record(name="RPDO Communication Parameter")
        param_record[1] = Variable(
            DT.UNSIGNED32, "rw", self._cob_id, name="COB-ID used by RPDO"
        )
        param_record[2] = Variable(
            DT.UNSIGNED8, "rw", self._transmission_type, name="Transmission Type"
        )
        od[0x1400 + index] = param_record

        od.download_callbacks[(0x1400 + index, 1)].add(self._downloaded_cob_id)
        od.download_callbacks[(0x1400 + index, 2)].add(
            self._downloaded_transmission_type
        )

        map_var = Variable(DT.UNSIGNED32, "rw", name="Application Object")
        map_array = Array(
            map_var, length=8, mutable=True, name="RPDO Mapping Parameter"
        )
        od[0x1600 + index] = map_array

        od.write(
            0x1600 + index, 0, 0, downloaded=False
        )  # set number of mapped objects to 0
        od.download_callbacks[(0x1600 + index, 0)].add(self._downloaded_map_length)

        node.nmt.state_callbacks.add(self._update_nmt_state)

    def _update_nmt_state(self, state: StateEnum):
        if state == StateEnum.OPERATIONAL:
            if self._index < 4:
                self._cob_id = (
                    (self._cob_id & 0xE000_0000)
                    + 0x200
                    + (self._index * 0x100)
                    + self._node.node_id
                )

            self._activate_mapping()
        else:
            self._deactivate_mapping()

    def _downloaded_cob_id(self, value: int):
        self._cob_id = value

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
        self._deactivate_mapping()
        self._transmission_type = value
        self._activate_mapping()

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

        self._node.object_dictionary.write(
            0x1400 + self._index, 1, self._cob_id, downloaded=False
        )

    def _downloaded_map_length(self, length):
        multiplexors = list()

        for subindex in range(1, length + 1):
            value = self._node.object_dictionary.read(0x1600 + self._index, subindex)
            index, subindex = value >> 16, (value >> 8) & 0xFF
            multiplexors.append((index, subindex))

        self._map(multiplexors)

    @property
    def mapping(self):
        return self._multiplexors

    @mapping.setter
    def mapping(self, multiplexors: TMultiplexor):
        self._map(multiplexors)
        self._node.object_dictionary.write(
            0x1600 + self._index, 0, len(multiplexors), downloaded=False
        )
        for _entry, multiplexor in enumerate(multiplexors):
            index, subindex = multiplexor
            variable = self._node.object_dictionary.lookup(index, subindex)
            value = (index << 16) + (subindex << 8) + variable.size
            self._node.object_dictionary.write(
                0x1600 + self._index, _entry + 1, value, downloaded=False
            )

    def _map(self, multiplexors: TMultiplexor):
        self._deactivate_mapping()
        self._multiplexors = tuple(multiplexors)
        self._activate_mapping()

    def _deactivate_mapping(self):
        if self._unpack_function is None:
            return

        self._unpack_function = None

        if self._on_sync in self._node.sync.callbacks:
            self._node.sync.callbacks.remove(self._on_sync)

        self._node.adapter.remove_subscription(cob_id=self._cob_id & 0x1FFF_FFFF)

    def _activate_mapping(self):
        if self._unpack_function is not None:
            return

        if self._cob_id & (1 << 31) or not self._multiplexors:
            return

        if self._node.nmt.state != StateEnum.OPERATIONAL:
            return

        variables = []
        for multiplexor in self._multiplexors:
            variable = self._node.object_dictionary.lookup(*multiplexor)
            variables.append(variable)

        def unpack(data: bytes):
            values = []
            for variable in variables:
                values.append(variable.unpack(data[: variable.size]))
                data = data[variable.size :]

            return values

        self._unpack_function = unpack

        if self._transmission_type <= 240:
            self._node.sync.callbacks.add(self._on_sync)

        self._node.adapter.add_subscription(
            cob_id=self._cob_id & 0x1FFF_FFFF, callback=self._handle_msg
        )

    def _on_sync(self):
        if self._synced_msg is None:
            return

        self._write_data(self._synced_msg)
        self._synced_msg = None

    def _handle_msg(self, cob_id: int, msg: bytes):
        if self._transmission_type <= 240:
            self._synced_msg = msg
            return

        self._write_data(msg)

    def _write_data(self, msg: bytes):
        values = self._unpack_function(msg)

        for multiplexor, value in zip(self._multiplexors, values):
            try:
                self._node.object_dictionary.write(*multiplexor, value)
            except:  # there is no possibility to response in such a case
                pass
