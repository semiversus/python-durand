from typing import TYPE_CHECKING
import struct

from durand.object_dictionary import Variable
from durand.services.nmt import StateEnum
from durand.datatypes import DatatypeEnum as DT
from durand.scheduler import get_scheduler

if TYPE_CHECKING:
    from durand.node import Node


class EMCY:
    def __init__(self, node: "Node"):
        self._node = node

        self._timer_handle = None
        self._inhibit_time = 0
        self._deferred_emcy = None

        self._cob_id = 0x80 + node.node_id

        node.object_dictionary[0x1001] = Variable(
            DT.UNSIGNED8, "ro", 0, name="Error Register"
        )
        node.object_dictionary[0x1014] = Variable(
            DT.UNSIGNED32, "rw", self._cob_id, name="COB-ID EMCY"
        )
        node.object_dictionary[0x1015] = Variable(
            DT.UNSIGNED16, "rw", self._inhibit_time, name="Inhibit Time EMCY"
        )

        node.object_dictionary.download_callbacks[(0x1014, 0)].add(
            self._downloaded_cob_id
        )
        node.object_dictionary.update_callbacks[(0x1015, 0)].add(
            self._update_inhibit_time
        )

        node.nmt.state_callbacks.add(self._update_nmt_state)

    def _downloaded_cob_id(self, value: int):
        self._cob_id = value

    def _update_nmt_state(self, state: StateEnum):
        if state == StateEnum.STOPPED:
            self._cob_id = None
        elif (
            state in (StateEnum.PRE_OPERATIONAL, StateEnum.OPERATIONAL)
            and self._cob_id is None
        ):
            self._cob_id = 0x80 + self._node.node_id

    @property
    def cob_id(self):
        return self._cob_id

    @cob_id.setter
    def cob_id(self, value: int):
        self._cob_id = value

    @property
    def enable(self) -> bool:
        return not self._cob_id & (1 << 31)

    @enable.setter
    def enable(self, value: bool):
        if value:
            self._cob_id &= ~(1 << 31)
        else:
            self._cob_id |= 1 << 31

        self._node.object_dictionary.write(0x1014, 0, self._cob_id, downloaded=False)

    def _update_inhibit_time(self, value: int):
        if self._timer_handle is not None:
            get_scheduler().cancel(self._timer_handle)
        self._timer_handle = None
        self._inhibit_time = value / 10_000

    @property
    def inhibit_time(self):
        return self._node.object_dictionary.read(0x1015, 0) / 10_000

    @inhibit_time.setter
    def inhibit_time(self, value: float):
        self._node.object_dictionary.write(0x1015, 0, value * 10_000, downloaded=False)

    def _time_up(self):
        self._timer_handle = None

        if self._deferred_emcy:
            self._send(*self._deferred_emcy)

        self._deferred_emcy = None

    def set(self, error_code: int, error_register: int, data: bytes = b""):
        self._node.object_dictionary.write(0x1001, 0, error_register, downloaded=False)

        if not self.enable:
            return

        if self._timer_handle is not None:
            self._deferred_emcy = (error_code, error_register, data)
            return

        self._send(error_code, error_register, data)

    def _send(self, error_code: int, error_register: int, data: bytes = b""):
        if self._inhibit_time:
            self._timer_handle = get_scheduler().add(self._inhibit_time, self._time_up)

        msg = (
            struct.pack("<HB", error_code, error_register) + data + bytes(5 - len(data))
        )
        self._node.adapter.send(self._cob_id, msg)
