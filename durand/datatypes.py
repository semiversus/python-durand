from struct import Struct
from enum import IntEnum


class DatatypeEnum(IntEnum):
    BOOLEAN = 1
    INTEGER8 = 2
    INTEGER16 = 3
    INTEGER32 = 4
    UNSIGNED8 = 5
    UNSIGNED16 = 6
    UNSIGNED32 = 7
    REAL32 = 8
    DOMAIN = 15


struct_dict = {
    DatatypeEnum.UNSIGNED8: Struct('B'),
    DatatypeEnum.INTEGER8: Struct('b'),
    DatatypeEnum.UNSIGNED16: Struct('<H'),
    DatatypeEnum.INTEGER16: Struct('<h'),
    DatatypeEnum.UNSIGNED32: Struct('<I'),
    DatatypeEnum.INTEGER32: Struct('<i'),
    DatatypeEnum.REAL32: Struct('<f')
}
