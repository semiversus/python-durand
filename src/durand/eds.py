from dataclasses import dataclass, fields
from re import match
from datetime import datetime
from typing import TYPE_CHECKING

from durand.object_dictionary import Variable, Record
from durand.datatypes import DatatypeEnum


if TYPE_CHECKING:
    from durand.node import Node


def datetime_to_time(d: datetime):
    return d.strftime("%I:%M") + ("AM" if d.hour < 12 else "PM")


def datetime_to_date(d: datetime):
    return d.strftime("%m-%d-%Y")


@dataclass
class FileInfo:
    FileName: str = "python_durand_device.eds"
    FileVersion: int = 0
    FileRevision: int = 0
    EDSVersion: str = "4.0"
    Description: str = None
    CreationTime: str = None
    CreationDate: str = None
    CreatedBy: str = None
    ModificationTime: str = None
    ModificationDate: str = None
    ModifiedBy: str = None

    def validate(self):
        if not 0 <= self.FileVersion <= 255:
            raise ValueError("FileVersion is Unsigned8")
        if not 0 <= self.FileRevision <= 255:
            raise ValueError("FileRevision is Unsigned8")
        if not match("[d].[d]", self.EDSVersion):
            raise ValueError("EDSVersion type mismatch")

        if self.CreationDate:
            try:
                datetime.strptime("%m-%d-%Y", self.CreationDate)
            except ValueError:
                raise ValueError("CreationDate format invalid")

        if self.CreationTime:
            if len(self.CreationTime) != 7 or self.CreationTime[5:] not in ("AM", "PM"):
                raise ValueError("CreationTime format invalid")

            try:
                datetime.strptime("%I:%M", self.CreationTime[:6])
            except ValueError:
                raise ValueError("CreationTime format invalid")

        if self.ModificationDate:
            try:
                datetime.strptime("%m-%d-%Y", self.ModificationDate)
            except ValueError:
                raise ValueError("ModificationDate format invalid")

        if self.ModificationTime:
            if len(self.ModificationTime) != 7 or self.ModificationTime[5:] not in (
                "AM",
                "PM",
            ):
                raise ValueError("ModificationTime format invalid")

            try:
                datetime.strptime("%I:%M", self.ModificationTime[:6])
            except ValueError:
                raise ValueError("ModificationTime format invalid")

    @property
    def content(self):
        content = "[FileInfo]\n"

        for field in fields(self):
            value = getattr(self, field.name)
            if value is None:
                continue

            content += f"{field.name}={value!s}\n"

        return content + "\n"


@dataclass
class DeviceInfo:
    VendorName: str = None

    @property
    def content(self):
        return "[DeviceInfo]\n\n"


def extract_objects(d: dict, indices: list) -> dict:
    extracted_dict = {index: obj for index, obj in d.items() if index in indices}
    for index in indices:
        d.pop(index, None)

    return extracted_dict


def describe_variable(index: int, subindex: int, variable: Variable) -> str:
    name = f"{index:04X}" + ("" if subindex is None else f"sub{subindex}")
    content = f"[{name}]\n"

    if variable.name:
        content += f"ParameterName={variable.name}\n"
    else:
        content += f"ParameterName=Variable{name}\n"

    content += "ObjectType=0x7\n"
    content += f"DataType=0x{variable.datatype}\n"
    content += f"AccessType={variable.access}\n"

    if variable.value is not None:
        content += f"DefaultValue={variable.value}\n"

    if variable.minimum is not None:
        content += f"LowLimit={variable.minimum}\n"

    if variable.maximum is not None:
        content += f"HighLimit={variable.maximum}\n"

    content += "PDOMapping=1\n\n"

    return content


def describe_object(index: int, object) -> str:
    if isinstance(object, Variable):
        return describe_variable(index, None, object)

    content = f"[{index:04X}]\nSubNumber={len(object)}\n"

    if object.name:
        content += f"ParameterName={object.name}\n"
    else:
        content += f"ParameterName=Object{index:04X}\n"

    content += (
        "ObjectType=0x8\n\n" if isinstance(object, Record) else "ObjectType=0x9\n\n"
    )

    for subindex, variable in object:
        content += describe_variable(index, subindex, variable)

    return content


def describe_section(name: str, objects: dict):
    content = f"[{name}]\nSupportedObjects={len(objects)}\n"

    for obj_nr, index in enumerate(objects):
        content += f"{obj_nr + 1}=0x{index:04X}\n"

    content += "\n"

    for index, object in objects.items():
        content += describe_object(index, object)

    return content


class EDS:
    def __init__(self, node: "Node"):
        self._node = node

        self.file_info = FileInfo()
        self.device_info = DeviceInfo()
        self.comments = ""

    @property
    def content(self):
        content = self.file_info.content

        content += self.device_info.content

        if self.comments:
            lines = self.comments.strip().splitlines()
            content += f"[Comments]\nLines={len(lines)}\n"
            for index, line in enumerate(lines):
                content += f"Line{index + 1}={line:s}\n"
            content += "\n"

        objects = dict(self._node.object_dictionary)

        mandatory_objects = extract_objects(objects, (0x1000, 0x1001, 0x1018))
        content += describe_section("MandatoryObjects", mandatory_objects)

        optional_indicies = [
            index for index in objects if index < 0x2000 or index >= 0x6000
        ]
        optional_objects = extract_objects(objects, optional_indicies)
        content += describe_section("OptionalObjects", optional_objects)

        content += describe_section("ManufacturerObjects", objects)

        return content


class EDSProvider:
    def __init__(self, node: "Node"):
        self._node = node
