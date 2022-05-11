from dataclasses import dataclass, fields
from re import match
from datetime import datetime

from durand import Node, Variable, DatatypeEnum


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
        content = '[FileInfo]\n'
        for field in fields(self):
            content += f'{field.name}={getattr(self, field.name):s}\n'
        return content


def extract_objects(d: dict, indices: list) -> dict:
    extracted_dict = {index: obj for index, obj in d if index in indices}
    for index in indices:
        d.pop(index, None)

    return extracted_dict

def describe_variable(index: int, subindex: int, variable: Variable) -> str:
    name = '{index:04X}' + ('' if subindex is None else f'sub{subindex}')
    content = f'[{name}]\n'

    if variable.name:
        content += f'ParameterName={variable.name}'
    else:
        content += f'ParameterName=Variable{name}'

    content += 'ObjectType=0x7\n'
    content += f'Datatype=0x{variable.datatype}\n'
    content += f'AccessType={variable.access}\n'
    if variable.value is not None:
        content += f'DefaultValue={variable.value}'
    content += 'PDOMapping=1\n'
    return content

def describe_object(index: int, object) -> str:
    if isinstance(object, Variable):
        return describe_variable(index, None, object)

def describe_section(name: str, objects: dict):
    content = f'[{name}]\nSupportedObjects={len(objects)}\n'

    for obj_nr, index in enumerate(objects):
        content += f'{obj_nr}=0x{index:04X}\n'

    content += '\n'

    for index, object in objects.items():
        content += describe_object(index, object)
        content += '\n'


class EDS:
    def __init__(self, node: 'Node'):
        self._node = node

        self.file_info = FileInfo()
        self.comments = ""

    @property
    def content(self):
        content = self.file_info.content + '\n'

        if self.comments:
            lines = self.comments.strip().splitlines()
            content += f'[Comments]\nLines={len(lines)}\n'
            for index, line in enumerate(lines):
                content += f'Line{index}={line:s}\n'
            content += '\n'

        objects = dict(self._node.object_dictionary)

        mandatory_objects = extract_objects(objects, (0x1000, 0x1001, 0x1018))
        content += describe_section('MandatoryObjects', mandatory_objects)






class EDSProvider:
    def __init__(self, node: Node, eds: EDS = None):
        self._node = node

        self._node.object_dictionary[0x1021] = Variable(DatatypeEnum.DOMAIN, "ro")
