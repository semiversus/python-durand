from typing import TYPE_CHECKING, Sequence, Callable, Any, Optional

from durand.object_dictionary import Variable, Record, Array
from durand.datatypes import DatatypeEnum as DT

from .base import PDOBase

if TYPE_CHECKING:
    from durand.node import Node


class RPDO(PDOBase):
    COB_OFFSET = 0x200
    MAPPING_ARRAY_INDEX = 0x1600

    def __init__(self, node: "Node", index: int):
        PDOBase.__init__(self, node, index)

        if index < 4:
            self._cob_id = 0x0000_0200 + (index * 0x100) + node.node_id
        else:
            self._cob_id = 0x8000_0000

        self._unpack_function: Optional[Callable[[bytes], Sequence[Any]]] = None
        self._synced_msg: Optional[bytes] = None

        od = self._node.object_dictionary

        param_record = Record(name=f"RPDO {index + 1} Communication Parameter")
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

        map_var = Variable(DT.UNSIGNED32, "rw", name="Mapped Object")
        map_array = Array(
            map_var, length=8, mutable=True, name=f"RPDO {index + 1} Mapping Parameter"
        )
        od[0x1600 + index] = map_array

        od.write(0x1600 + index, 0, 0)  # set number of mapped objects to 0
        od.download_callbacks[(0x1600 + index, 0)].add(self._downloaded_map_length)

        node.nmt.state_callbacks.add(self._update_nmt_state)

    def _set_transmission_type(self, value: int):
        self._deactivate_mapping()
        self._transmission_type = value
        self._node.object_dictionary.write(0x1400 + self._index, 2, value)
        self._activate_mapping()

    def _update_od_cob_id(self):
        self._node.object_dictionary.write(0x1400 + self._index, 1, self._cob_id)

    def _deactivate_mapping(self):
        if self._unpack_function is None:
            return

        self._unpack_function = None

        if self._on_sync in self._node.sync.callbacks:
            self._node.sync.callbacks.remove(self._on_sync)

        self._node.network.remove_subscription(cob_id=self._cob_id & 0x1FFF_FFFF)

    def _activate_mapping(self):
        if not self._validate_state():
            return

        if self._unpack_function is not None:
            return

        expected_size = 0
        variables = []

        for multiplexor in self._multiplexors:
            variable = self._node.object_dictionary.lookup(*multiplexor)
            variables.append(variable)
            expected_size += variable.size

        def unpack(data: bytes):
            if len(data) != expected_size:
                self.node.emcy.set(0x8210, 0)  # EMCY for RPDO with wrong size
                return

            values = []
            for variable in variables:
                values.append(variable.unpack(data[: variable.size]))
                data = data[variable.size :]

            return values

        self._unpack_function = unpack

        if self._transmission_type <= 240:
            self._node.sync.callbacks.add(self._on_sync)

        self._node.network.add_subscription(
            cob_id=self._cob_id & 0x1FFF_FFFF, callback=self._handle_msg
        )

    def _on_sync(self):
        if self._synced_msg is None:
            return

        self._write_data(self._synced_msg)
        self._synced_msg = None

    def _handle_msg(self, _cob_id: int, msg: bytes):
        if self._transmission_type <= 240:
            self._synced_msg = msg
            return

        self._write_data(msg)

    def _write_data(self, msg: bytes):
        assert self._unpack_function is not None, "RPDO should be deactivated"
        values = self._unpack_function(msg)

        if values is None:
            return

        for multiplexor, value in zip(self._multiplexors, values):
            try:
                self._node.object_dictionary.write(*multiplexor, value, downloaded=True)
            except:  # there is no possibility to response in such a case
                pass
