from dataclasses import dataclass
from collections import defaultdict
from typing import Any, Dict, List, Tuple, Callable
import logging

from .datatypes import DatatypeEnum, struct_dict


log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Variable:
    index: int
    subindex: int
    datatype: DatatypeEnum
    access: str
    default: Any = 0
    factor: float = 1
    minimum: float = None
    maximum: float = None

    def __post_init__(self):
        if not 0 <= self.index <= 0xFFFF:
            raise ValueError('Index has to UINT16')
        if not 0 <= self.subindex <= 255:
            raise ValueError('Subindex has to be UINT8')
        if self.datatype not in DatatypeEnum:
            raise ValueError('Unsupported datatype')
        if self.access not in ('rw', 'ro', 'wo', 'const'):
            raise ValueError('Invalid access type')

    @property
    def multiplexor(self):
        return (self.index, self.subindex)

    @property
    def writable(self):
        return self.access in ('wo', 'rw')

    @property
    def readable(self):
        return self.access in ('ro', 'rw', 'const')

    @property
    def size(self) -> int:
        return struct_dict[self.datatype].size

    def on_read(self, od: 'ObjectDictionary'):
        # it's called via @variable.on_read(od) wrapping a function
        def wrap(func):
            od.set_read_callback(self, func)
        return wrap

    def on_update(self, od: 'ObjectDictionary'):
        # it's called via @variable.on_update(od) wrapping a function
        def wrap(func):
            od.add_update_callback(self, func)
        return wrap

    def pack(self, value) -> bytes:
        value = int(value / self.factor)
        dt_struct = struct_dict[self.datatype]
        return dt_struct.pack(value)

    def unpack(self, data: bytes):
        dt_struct = struct_dict[self.datatype]
        value = dt_struct.unpack(data)[0]
        value *= self.factor
        return value


class ObjectDictionary:
    def __init__(self):
        self._variables: Dict[Tuple[int, int], Variable] = dict()
        self._data: Dict[Variable, Any] = dict()

        self._validate_callbacks: Dict[Variable, List[Callable]] = \
            defaultdict(list)
        self._update_callbacks: Dict[Variable, List[Callable]] = \
            defaultdict(list)
        self._download_callbacks: Dict[Variable, List[Callable]] = \
            defaultdict(list)
        self._read_callbacks: Dict[Variable, Callable] = dict()

    def add_object(self, variable: Variable):
        self._variables[variable.multiplexor] = variable
        self._data[variable] = 0

        if variable.subindex == 0:
            return

        if (variable.index, 0) in self._variables:
            largest_subindex = self._variables[(variable.index, 0)]
        else:
            largest_subindex = Variable(
                index=variable.index, subindex=0,
                datatype=DatatypeEnum.UNSIGNED8, access='const')

            self._variables[(variable.index, 0)] = largest_subindex

        value = max(self._data.get(largest_subindex, 0),  variable.subindex)
        self._data[largest_subindex] = value

    def lookup(self, index: int, subindex: int = 0) -> Variable:
        return self._variables[(index, subindex)]

    def write(self, variable: Variable, value: Any, downloaded: bool=True):
        for callback in self._validate_callbacks[variable]:
            callback(value)  # may raises a exception

        self._data[variable] = value

        for callback in self._update_callbacks[variable]:
            try:
                callback(value)
            except Exception as e:
                log.exception(f'Writing {value!r} to {variable!r} raised an {e!r}')

        if not downloaded:
            return

        for callback in self._download_callbacks[variable]:
            try:
                callback(value)
            except Exception as e:
                log.exception(f'Writing {value!r} to {variable!r} raised an {e!r}')

    def add_validate_callback(self, variable: Variable, callback):
        self._validate_callbacks[variable].append(callback)

    def remove_validate_callback(self, variable: Variable, callback):
        self._validate_callbacks[variable].remove(callback)

    def add_download_callback(self, variable: Variable, callback):
        self._download_callbacks[variable].append(callback)

    def remove_download_callback(self, variable: Variable, callback):
        self._download_callbacks[variable].remove(callback)

    def add_update_callback(self, variable: Variable, callback):
        self._update_callbacks[variable].append(callback)

    def remove_update_callback(self, variable: Variable, callback):
        self._update_callbacks[variable].remove(callback)

    def read(self, variable: Variable):
        if variable in self._read_callbacks:
            return self._read_callbacks[variable]()

        return self._data[variable]

    def set_read_callback(self, variable: Variable, callback) -> None:
        self._read_callbacks[variable] = callback

    @property
    def variables(self) -> Tuple[Variable]:
        return tuple(self._variables.keys())
