from dataclasses import dataclass, field
from collections import defaultdict
from typing import Any, Dict, Tuple, Callable, Union
import itertools
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
    name: str = None

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


class Record:
    def __init__(self, name: str = None):
        self.name = name
        self._variables: Dict[int, Variable] = dict()

    def __getitem__(self, subindex: int):
        if subindex == 0:
            value = max(self._variables) if self._variables else 0
            return Variable(
                DatatypeEnum.UNSIGNED8,
                "const",
                value=value,
                name="Highest Sub-Index Supported",
            )

        return self._variables[subindex]

    def __setitem__(self, subindex: int, variable: Variable):
        self._variables[subindex] = variable

    def __iter__(self):
        variables = [(0, self[0])]
        variables += list(sorted(self._variables.items(), key=lambda n: n[0]))
        return variables.__iter__()

    def __len__(self):
        return len(self._variables) + 1

    def __contains__(self, subindex: int):
        return subindex == 0 or subindex in self._variables


class Array:
    def __init__(
        self, variable: Variable, length: int, mutable: bool = False, name: str = None
    ):
        self.name = name
        self._variable = variable
        self._mutable = mutable
        self.length = length

    def __getitem__(self, subindex: int):
        if subindex == 0:
            access = "rw" if self._mutable else "const"
            return Variable(
                DatatypeEnum.UNSIGNED8,
                access,
                value=self.length,
                name="Highest Sub-Index Supported",
            )

        if subindex > self.length:
            raise KeyError(f"Subindex {subindex} not available in array")

        return self._variable

    def __iter__(self):
        variables = [(0, self[0])]
        variables += [(i + 1, self._variable) for i in range(self.length)]
        return variables.__iter__()

    def __len__(self):
        return self.length + 1

    def __contains__(self, subindex: int):
        return subindex <= self.length


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
        except KeyError:
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

    def __iter__(self):
        objects = itertools.chain(self._objects.items(), self._variables.items())
        return iter(sorted(objects, key=lambda n: n[0]))

    def __len__(self):
        return len(self._objects) + len(self._variables)

    def __contains__(self, index: int):
        return index in self._objects or index in self._variables
