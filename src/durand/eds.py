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
        content += '[MandatoryObjects]\nSupportedObjects=3\n1=0x1000\n2=0x1001\n3=0x1018\n\n'





class EDSProvider:
    def __init__(self, node: Node, eds: EDS = None):
        self._node = node

        self._node.object_dictionary[0x1021] = Variable(DatatypeEnum.DOMAIN, "ro")
