from typing import TYPE_CHECKING
import logging

from durand.object_dictionary import TMultiplexor, Variable, Record, Array
from durand.datatypes import DatatypeEnum as DT
from durand.services.nmt import StateEnum
from durand import get_scheduler

if TYPE_CHECKING:
    from durand.node import Node


log = logging.getLogger(__name__)


class InhibitTimer:
    def __init__(self, duration: float):
        self._timer_id = None
        self._duration = duration
        self._retrigger_callback = None

    def trigger(self, retrigger_callback):
        if self._timer_id is None:
            self._timer_id = get_scheduler().add(self._duration, self._time_up)
        else:
            self._retrigger_callback = retrigger_callback

    def cancel(self):
        if self._timer_id is not None:
            get_scheduler().cancel(self._timer_id)

        self._timer_id = None

    def _time_up(self):
        self._timer_id = None
        callback = self._retrigger_callback
        self._retrigger_callback = None

        if callback:
            callback()

    def is_active(self):
        return self._timer_id is not None


class SyncHandler:
    """SyncHandler is handling transmission types using the SYNC protocol
    mode 0: divider is 0 and _counter will be used to detect a changed datafield
    mode 1-240: every nth sync a transmit is executed
    """

    def __init__(self, tpdo: "TPDO", divider: int):
        tpdo._node.sync.callbacks.add(self._on_sync)
        self._tpdo = tpdo
        self._counter = 0
        self._divider = divider

    def cancel(self):
        self._tpdo._node.sync.callbacks.remove(self._on_sync)

    def _on_sync(self):
        if self._divider:
            self._counter += 1
            if self._counter >= self._divider:
                self._tpdo.transmit()
        else:
            if self._counter:
                self._tpdo.transmit()
            self._counter = 0

    def update(self):
        self._counter += 1


class TPDO:
    def __init__(self, node: "Node", index: int):
        self._node = node
        self._index = index

        if index < 4:
            self._cob_id = 0x4000_0180 + (index * 0x100) + node.node_id
        else:
            self._cob_id = 0xC000_0000

        self._transmission_type = 255

        self._multiplexors = ()
        self._pack_functions = None
        self._cache = None

        self._sync_handler: SyncHandler = None
        self._inhibit_timer: InhibitTimer = None

        od = self._node.object_dictionary

        param_record = Record(name="TPDO Communication Parameter")
        param_record[1] = Variable(
            DT.UNSIGNED32, "rw", self._cob_id, name="COB-ID used by TPDO"
        )
        param_record[2] = Variable(
            DT.UNSIGNED8, "rw", self._transmission_type, name="Transmission Type"
        )
        param_record[3] = Variable(DT.UNSIGNED16, "rw", 0, name="Inhibit Time")
        od[0x1800 + index] = param_record

        od.download_callbacks[(0x1800 + index, 1)].add(self._downloaded_cob_id)
        od.download_callbacks[(0x1800 + index, 2)].add(
            self._downloaded_transmission_type
        )
        od.update_callbacks[(0x1800 + index, 3)].add(self._update_inhibit_time)

        map_var = Variable(DT.UNSIGNED32, "rw", name="Application Object")
        map_array = Array(
            map_var, length=8, mutable=True, name="TPDO Mapping Parameter"
        )
        od[0x1A00 + index] = map_array

        od.write(
            0x1A00 + index, 0, 0, downloaded=False
        )  # set number of mapped objects to 0
        od.download_callbacks[(0x1A00 + index, 0)].add(self._downloaded_map_length)

        node.nmt.state_callbacks.add(self._update_nmt_state)

    def _update_nmt_state(self, state: StateEnum):
        if state == StateEnum.OPERATIONAL:
            if self._index < 4:
                self._cob_id = (
                    (self._cob_id & 0xE000_0000)
                    + 0x180
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
        if self._sync_handler:
            self._sync_handler.cancel()
            self._sync_handler = None

        if value <= 240:
            self._sync_handler = SyncHandler(self, value)

        self._transmission_type = value

    def _update_inhibit_time(self, value: int):
        if self._inhibit_timer:
            self._inhibit_timer.cancel()
            self._inhibit_timer = None

        if value:
            self._inhibit_timer = InhibitTimer(value * 0.000_1)  # value is [100µs]

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
            0x1800 + self._index, 1, self._cob_id, downloaded=False
        )

    @property
    def inhibit_time(self):
        return self._node.object_dictionary.read(0x1800 + self._index, 3) * 0.000_1

    @inhibit_time.setter
    def inhibit_time(self, value: float):
        return self._node.object_dictionary.write(
            0x1800 + self._index, 3, value * 10_000, downloaded=False
        )

    def _downloaded_map_length(self, length):
        multiplexors = list()

        for subindex in range(1, length + 1):
            value = self._node.object_dictionary.read(0x1A00 + self._index, subindex)
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
            0x1A00 + self._index, 0, len(multiplexors), downloaded=False
        )
        for _entry, multiplexor in enumerate(multiplexors):
            index, subindex = multiplexor
            variable = self._node.object_dictionary.lookup(index, subindex)
            value = (index << 16) + (subindex << 8) + variable.size
            self._node.object_dictionary.write(
                0x1A00 + self._index, _entry + 1, value, downloaded=False
            )

    def _map(self, multiplexors: TMultiplexor):
        self._deactivate_mapping()
        self._multiplexors = tuple(multiplexors)
        self._activate_mapping()

    def _deactivate_mapping(self):
        if self._cache is None:  # check if already deactivated
            return

        if self._inhibit_timer:
            self._inhibit_timer.cancel()

        update_callbacks = self._node.object_dictionary.update_callbacks

        for multiplexor, function in zip(self._multiplexors, self._pack_functions):
            update_callbacks[multiplexor].remove(function)

        self._cache = None
        self._pack_functions = None

    def _activate_mapping(self):
        if self._cache is not None:  # check if already activated
            return

        if self._cob_id & (1 << 31) or not self._multiplexors:
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
                if self._transmission_type == 255:
                    self.transmit()
                elif self._transmission_type == 0:
                    self._sync_handler.update()

            value = self._node.object_dictionary.read(*multiplexor)
            self._cache.append(variable.pack(value))
            self._pack_functions.append(pack)
            update_callbacks[multiplexor].add(pack)

        if self._transmission_type == 255:
            self.transmit()
        elif self._transmission_type == 0:
            self._sync_handler.update()

    def transmit(self):
        if self._inhibit_timer:
            already_active = self._inhibit_timer.is_active()
            self._inhibit_timer.trigger(self.transmit)
            if already_active:
                return

        data = b"".join(self._cache)
        self._node.adapter.send(self._cob_id & 0x1FFF_FFFF, data)
