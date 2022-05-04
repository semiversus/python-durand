from dataclasses import dataclass, field
from collections import defaultdict
from typing import Any, Dict, Tuple, Callable, Union
import logging

from .datatypes import DatatypeEnum, struct_dict, is_numeric, is_float
from .callback_handler import CallbackHandler, FailMode


log = logging.getLogger(__name__)


TMultiplexor = Union[int, Tuple[int, int]]


@dataclass
class Variable:
    datatype: DatatypeEnum
    access: str
    value: Any = None
    factor: float = 1
    minimum: float = None
    maximum: float = None

    def __post_init__(self):
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


@dataclass
class Record:
    variables: Dict[int, Variable] = field(default_factory=dict)

    def __getitem__(self, subindex: int):
        return self.variables[subindex]

    def __setitem__(self, subindex: int, variable: Variable):
        self.variables[subindex] = variable

    def add_largest_subindex(self, access="const"):
        largest_subindex = max(self.variables)
        self[0] = Variable(DatatypeEnum.UNSIGNED8, access, value=largest_subindex)


@dataclass
class Array:
    variables: Dict[int, Variable] = field(default_factory=dict)

    def __getitem__(self, subindex: int):
        return self.variables[subindex]

    def __setitem__(self, subindex: int, variable: Variable):
        self.variables[subindex] = variable


TObject = Union[Variable, Record, Array]


class ObjectDictionary:
    def __init__(self):
        self._variables: Dict[TMultiplexor, Variable] = dict()
        self._objects: Dict[int, TObject] = dict()
        self._data: Dict[TMultiplexor, Any] = dict()

        self.validate_callbacks: Dict[TMultiplexor, CallbackHandler] = defaultdict(
            lambda: CallbackHandler(fail_mode=FailMode.FIRST_FAIL)
        )
        self.update_callbacks: Dict[TMultiplexor, CallbackHandler] = defaultdict(
            CallbackHandler
        )
        self.download_callbacks: Dict[TMultiplexor, CallbackHandler] = defaultdict(
            CallbackHandler
        )
        self._read_callbacks: Dict[TMultiplexor, Callable] = dict()

    def __getitem__(self, index: int):
        try:
            return self._variables[index]
        except IndexError:
            return self._objects[index]

    def __setitem__(self, index: int, object: TObject):
        if isinstance(object, Variable):
            self._variables[index] = object
        else:
            self._objects[index] = object

    def lookup(self, index: int, subindex: int = None) -> Variable:
        try:
            return self._variables[index]
        except KeyError:
            if subindex is None:
                return self._objects[index]

            return self._objects[index][subindex]

    def write(self, index: int, subindex: int, value: Any, downloaded: bool = True):
        if index in self._variables:
            multiplexor = (index, 0)
        else:
            multiplexor = (index, subindex)

        if multiplexor in self.validate_callbacks:
            self.validate_callbacks[multiplexor].call(value)  # may raises exception

        self._data[multiplexor] = value

        if multiplexor in self.update_callbacks:
            self.update_callbacks[multiplexor].call(value)

        if not downloaded:
            return

        if multiplexor in self.download_callbacks:
            self.download_callbacks[multiplexor].call(value)

    def read(self, index: int, subindex: int):
        if index in self._variables:
            multiplexor = (index, 0)
        else:
            multiplexor = (index, subindex)

        if multiplexor in self._read_callbacks:
            return self._read_callbacks[multiplexor]()

        try:
            return self._data[multiplexor]
        except KeyError:
            variable = self.lookup(index, subindex)
            value = variable.value

            if value is None:
                value = 0 if is_numeric(variable.datatype) else b""

            return value

    def set_read_callback(self, index: int, subindex: int, callback) -> None:
        self._read_callbacks[(index, subindex)] = callback
