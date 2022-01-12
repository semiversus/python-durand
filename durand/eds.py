from dataclasses import dataclass
from re import match
from datetime import datetime

from durand import Node, Variable, DatatypeEnum


def datetime_to_time(d: datetime):
    return d.strftime('%I:%M') + ('AM' if d.hour < 12 else 'PM')

def datetime_to_date(d: datetime):
    return d.strftime('%m-%d-%Y')


@dataclass
class FileInfo:
    FileName: str = 'python_durand_device.eds'
    FileVersion: int = 0
    FileRevision: int = 0
    EDSVersion: str = '4.0'
    Description: str = None
    CreationTime: str = None
    CreationDate: str = None
    CreatedBy: str = None
    ModificationTime: str = None
    ModificationDate: str = None
    ModifiedBy: str = None

    Comment: str = None

    def validate(self):
        if not 0 <= self.FileVersion <= 255:
            raise ValueError('FileVersion is Unsigned8')
        if not 0 <= self.FileRevision <= 255:
            raise ValueError('FileRevision is Unsigned8')
        if not match('[d].[d]', self.EDSVersion):
            raise ValueError('EDSVersion type mismatch')

        if self.CreationDate:
            try:
                datetime.strptime('%m-%d-%Y', self.CreationDate)
            except ValueError:
                raise ValueError('CreationDate format invalid')

        if self.CreationTime:
            if len(self.CreationTime) != 7 or self.CreationTime[5:] not in ('AM', 'PM'):
                raise ValueError('CreationTime format invalid')

            try:
                datetime.strptime('%I:%M', self.CreationTime[:6])
            except ValueError:
                raise ValueError('CreationTime format invalid')

        if self.ModificationDate:
            try:
                datetime.strptime('%m-%d-%Y', self.ModificationDate)
            except ValueError:
                raise ValueError('ModificationDate format invalid')

        if self.ModificationTime:
            if len(self.ModificationTime) != 7 or self.ModificationTime[5:] not in ('AM', 'PM'):
                raise ValueError('ModificationTime format invalid')

            try:
                datetime.strptime('%I:%M', self.ModificationTime[:6])
            except ValueError:
                raise ValueError('ModificationTime format invalid')



class EDS:
    def __init__(self):
        self.FileInfo = FileInfo()


class EDSProvider:
    def __init__(self, node: Node, eds: EDS = None):
        self._node = node
        self.eds = eds or EDS()

        eds_store_variable = Variable(0x1021, 0, DatatypeEnum.DOMAIN, 'ro')
        self._node.object_dictionary.add_object(eds_store_variable)
        self._node.object_dictionary.set_read_callback(eds_store_variable, self.generate)
