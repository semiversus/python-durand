from dataclasses import dataclass, fields
from re import match
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from durand.object_dictionary import Variable, Record
from durand.datatypes import DatatypeEnum


if TYPE_CHECKING:
    from durand.node import Node


@dataclass
class FileInfo:
    FileName: str = "python_durand_device.eds"
    FileVersion: int = 0
    FileRevision: int = 0
    EDSVersion: str = "4.0"
    Description: Optional[str] = None
    CreationTime: Optional[str] = None
    CreationDate: Optional[str] = None
    CreatedBy: Optional[str] = None
    ModificationTime: Optional[str] = None
    ModificationDate: Optional[str] = None
    ModifiedBy: Optional[str] = None

    def validate(self):
        if not 0 <= self.FileVersion <= 255:
            raise ValueError("FileVersion is Unsigned8")
        if not 0 <= self.FileRevision <= 255:
            raise ValueError("FileRevision is Unsigned8")
        if not match(r"\d.\d", self.EDSVersion):
            raise ValueError("EDSVersion type mismatch")

        if self.CreationDate:
            try:
                datetime.strptime("%m-%d-%Y", self.CreationDate)
            except ValueError as exc:
                raise ValueError("CreationDate format invalid") from exc

        if self.CreationTime:
            if len(self.CreationTime) != 7 or self.CreationTime[5:] not in ("AM", "PM"):
                raise ValueError("CreationTime format invalid")

            try:
                datetime.strptime("%I:%M", self.CreationTime[:6])
            except ValueError as exc:
                raise ValueError("CreationTime format invalid") from exc

        if self.ModificationDate:
            try:
                datetime.strptime("%m-%d-%Y", self.ModificationDate)
            except ValueError as exc:
                raise ValueError("ModificationDate format invalid") from exc

        if self.ModificationTime:
            if len(self.ModificationTime) != 7 or self.ModificationTime[5:] not in (
                "AM",
                "PM",
            ):
                raise ValueError("ModificationTime format invalid")

            try:
                datetime.strptime("%I:%M", self.ModificationTime[:6])
            except ValueError as exc:
                raise ValueError("ModificationTime format invalid") from exc

    @property
    def content(self):
        self.validate()

        content = "[FileInfo]\n"

        for field in fields(self):
            value = getattr(self, field.name)
            if value is None:
                continue

            content += f"{field.name}={value!s}\n"

        return content + "\n"


@dataclass
class DeviceInfo:
    VendorName: Optional[str] = None
    VendorNumber: Optional[int] = None
    BaudRate_10: Optional[int] = None
    BaudRate_20: Optional[int] = None
    BaudRate_50: Optional[int] = None
    BaudRate_125: Optional[int] = None
    BaudRate_250: Optional[int] = None
    BaudRate_500: Optional[int] = None
    BaudRate_800: Optional[int] = None
    BaudRate_1000: Optional[int] = None
    SimpleBootUpMaster: int = 0
    SimpleBootUpSlave: int = 1
    Granularity: int = 8
    NrOfRXPDO: Optional[int] = None
    NrOfTXPDO: Optional[int] = None
    LSS_Supported: int = 1

    @property
    def content(self):
        content = "[DeviceInfo]\n"

        for field in fields(self):
            value = getattr(self, field.name)
            if value is None:
                continue

            content += f"{field.name}={value!s}\n"

        return content + "\n"


class EDS:
    def __init__(self, node: "Node"):
        self._node = node

        self.file_info = FileInfo()
        self.device_info = DeviceInfo()
        self.comments = ""

    replace_node_id = {
        (0x1014, None): 0x80,  # EMCY
        (0x1200, 1): 0x600,  # SDO Server COB Rx
        (0x1200, 2): 0x580,  # SDO Server COB Tx
        (0x1400, 1): 0x200,  # RPDO 1
        (0x1401, 1): 0x300,  # RPDO 2
        (0x1402, 1): 0x400,  # RPDO 3
        (0x1403, 1): 0x500,  # RPDO 4
        (0x1800, 1): 0x180,  # TPDO 1
        (0x1801, 1): 0x280,  # TPDO 2
        (0x1802, 1): 0x380,  # TPDO 3
        (0x1803, 1): 0x480,  # TPDO 4
    }

    @property
    def content(self):
        content = ""

        if self.comments:
            lines = self.comments.strip().splitlines()
            content += f"[Comments]\nLines={len(lines)}\n"
            for index, line in enumerate(lines):
                content += f"Line{index + 1}={line:s}\n"
            content += "\n"

        content += self.file_info.content
        content += self.device_info.content

        objects = dict(self._node.object_dictionary)

        mandatory_objects = self.extract_objects(objects, (0x1000, 0x1001, 0x1018))
        content += self.describe_section("MandatoryObjects", mandatory_objects)

        optional_indices = [
            index for index in objects if index < 0x2000 or index >= 0x6000
        ]
        optional_objects = self.extract_objects(objects, optional_indices)
        content += self.describe_section("OptionalObjects", optional_objects)

        content += self.describe_section("ManufacturerObjects", objects)

        return content

    @staticmethod
    def extract_objects(d: dict, indices: list) -> dict:
        extracted_dict = {index: obj for index, obj in d.items() if index in indices}
        for index in indices:
            d.pop(index, None)

        return extracted_dict

    def describe_variable(self, index: int, subindex: int, variable: Variable) -> str:
        name = f"{index:04X}" + ("" if subindex is None else f"sub{subindex}")
        content = f"[{name}]\n"

        if variable.name:
            content += f"ParameterName={variable.name}\n"
        else:
            content += f"ParameterName=Variable{name}\n"

        content += "ObjectType=0x7\n"
        content += f"DataType=0x{variable.datatype:X}\n"
        content += f"AccessType={variable.access}\n"

        if self._node.object_dictionary.has_value(index, subindex):
            value = self._node.object_dictionary.read(index, subindex)
        else:
            value = variable.value

        if (index, subindex) in EDS.replace_node_id:
            offset = EDS.replace_node_id[(index, subindex)]
            value = f"$NodeID+0x{offset:x}"

        if value is not None:
            if variable.datatype == DatatypeEnum.VISIBLE_STRING:
                value = value.decode()

            content += f"DefaultValue={value}\n"

        if variable.minimum is not None:
            content += f"LowLimit={variable.minimum}\n"

        if variable.maximum is not None:
            content += f"HighLimit={variable.maximum}\n"

        content += f"PDOMapping={0 if index < 0x2000 else 1}\n\n"

        return content

    def describe_object(self, index: int, obj) -> str:
        if isinstance(obj, Variable):
            return self.describe_variable(index, None, obj)

        content = f"[{index:04X}]\nSubNumber={len(obj)}\n"

        if obj.name:
            content += f"ParameterName={obj.name}\n"
        else:
            content += f"ParameterName=Object{index:04X}\n"

        content += (
            "ObjectType=0x8\n\n" if isinstance(obj, Record) else "ObjectType=0x9\n\n"
        )

        for subindex, variable in obj:
            content += self.describe_variable(index, subindex, variable)

        return content

    def describe_section(self, name: str, objects: dict):
        content = f"[{name}]\nSupportedObjects={len(objects)}\n"

        for obj_nr, index in enumerate(objects):
            content += f"{obj_nr + 1}=0x{index:04X}\n"

        content += "\n"

        for index, obj in objects.items():
            content += self.describe_object(index, obj)

        return content


class EDSProvider:
    def __init__(self, node: "Node"):
        self._node = node
