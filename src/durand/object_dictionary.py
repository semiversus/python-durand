from dataclasses import dataclass
from collections import defaultdict
from typing import Any, Dict, List, Tuple, Callable
import logging

from .datatypes import DatatypeEnum, struct_dict, is_numeric, is_float
from .callback_handler import CallbackHandler, FailMode


log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Variable:
    index: int
    subindex: int
    datatype: DatatypeEnum
    access: str
    default: Any = None
    factor: float = 1
    minimum: float = None
    maximum: float = None

    def __post_init__(self):
        if not 0 <= self.index <= 0xFFFF:
            raise ValueError("Index has to UINT16")
        if not 0 <= self.subindex <= 255:
            raise ValueError("Subindex has to be UINT8")
        if self.datatype not in DatatypeEnum:
            raise ValueError("Unsupported datatype")
        if self.access not in ("rw", "ro", "wo", "const"):
            raise ValueError("Invalid access type")
        if not is_numeric(self.datatype) and (
            self.maximum is not None or self.minimum is not None
        ):
            raise ValueError(
                "Minimum and Maximum not available with datatype %rs" % self.datatype
            )

    @property
    def multiplexor(self) -> Tuple[int, int]:
        return (self.index, self.subindex)

    @property
    def writable(self):
        return self.access in ("wo", "rw")

    @property
    def readable(self):
        return self.access in ("ro", "rw", "const")

    @property
    def size(self) -> int:
        if is_numeric(self.datatype):
            return struct_dict[self.datatype].size

        return None  # no size available

    def on_read(self, od: "ObjectDictionary"):
        # it's called via @variable.on_read(od) wrapping a function
        def wrap(func):
            od.set_read_callback(self, func)

        return wrap

    def on_update(self, od: "ObjectDictionary"):
        # it's called via @variable.on_update(od) wrapping a function
        def wrap(func):
            od.update_callbacks[self].add(func)

        return wrap

    def pack(self, value) -> bytes:
        if not is_numeric(self.datatype):
            return bytes(value)

        value = value / self.factor
        dt_struct = struct_dict[self.datatype]

        if not is_float(self.datatype):
            value = int(value)

        return dt_struct.pack(value)

    def unpack(self, data: bytes):
        if not is_numeric(self.datatype):
            return bytes(data)

        dt_struct = struct_dict[self.datatype]
        value = dt_struct.unpack(data)[0]
        value *= self.factor

        return value


class ObjectDictionary:
    def __init__(self):
        self._variables: Dict[Tuple[int, int], Variable] = dict()
        self._data: Dict[Variable, Any] = dict()

        self.validate_callbacks: Dict[Variable, CallbackHandler] = defaultdict(
            lambda: CallbackHandler(fail_mode=FailMode.FIRST_FAIL)
        )
        self.update_callbacks: Dict[Variable, CallbackHandler] = defaultdict(
            CallbackHandler
        )
        self.download_callbacks: Dict[Variable, CallbackHandler] = defaultdict(
            CallbackHandler
        )
        self._read_callbacks: Dict[Variable, Callable] = dict()

    def add_object(self, variable: Variable):
        self._variables[variable.multiplexor] = variable
        if variable.default is not None:
            self._data[variable] = variable.default
        else:
            self._data[variable] = 0 if is_numeric(variable.datatype) else b""

        if variable.subindex == 0:
            return

        if (variable.index, 0) in self._variables:
            largest_subindex = self._variables[(variable.index, 0)]
        else:
            largest_subindex = Variable(
                index=variable.index,
                subindex=0,
                datatype=DatatypeEnum.UNSIGNED8,
                access="const",
            )

            self._variables[(variable.index, 0)] = largest_subindex

        value = max(self._data.get(largest_subindex, 0), variable.subindex)
        self._data[largest_subindex] = value

    def lookup(self, index: int, subindex: int = 0) -> Variable:
        return self._variables[(index, subindex)]

    def write(self, variable: Variable, value: Any, downloaded: bool = True):
        self.validate_callbacks[variable].call(value)  # may raises exception
        self._data[variable] = value
        self.update_callbacks[variable].call(value)

        if not downloaded:
            return

        self.download_callbacks[variable].call(value)

    def read(self, variable: Variable):
        if variable in self._read_callbacks:
            return self._read_callbacks[variable]()

        return self._data[variable]

    def set_read_callback(self, variable: Variable, callback) -> None:
        self._read_callbacks[variable] = callback

    @property
    def variables(self) -> Tuple[Variable]:
        return tuple(self._variables.keys())
