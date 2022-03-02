from struct import Struct
from enum import IntEnum


class DatatypeEnum(IntEnum):
    BOOLEAN = 1
    INTEGER8 = 2
    INTEGER16 = 3
    INTEGER32 = 4
    INTEGER64 = 0x15
    UNSIGNED8 = 5
    UNSIGNED16 = 6
    UNSIGNED32 = 7
    UNSIGNED64 = 0x1B
    VISIBLE_STRING = 9
    OCTET_STRING = 10
    REAL32 = 8
    REAL64 = 0x11
    DOMAIN = 15


def is_numeric(datatype: DatatypeEnum):
    return datatype not in (DatatypeEnum.VISIBLE_STRING, DatatypeEnum.OCTET_STRING, DatatypeEnum.DOMAIN)

def is_float(datatype: DatatypeEnum):
    return datatype in (DatatypeEnum.REAL32, DatatypeEnum.REAL64)

struct_dict = {
    DatatypeEnum.UNSIGNED8: Struct('B'),
    DatatypeEnum.INTEGER8: Struct('b'),
    DatatypeEnum.UNSIGNED16: Struct('<H'),
    DatatypeEnum.INTEGER16: Struct('<h'),
    DatatypeEnum.UNSIGNED32: Struct('<I'),
    DatatypeEnum.INTEGER32: Struct('<i'),
    DatatypeEnum.UNSIGNED64: Struct('<Q'),
    DatatypeEnum.INTEGER64: Struct('<q'),
    DatatypeEnum.REAL32: Struct('<f'),
    DatatypeEnum.REAL64: Struct('<d'),
    DatatypeEnum.VISIBLE_STRING: Struct('s'),
    DatatypeEnum.OCTET_STRING: Struct('s'),
    DatatypeEnum.DOMAIN: Struct('s'),
}
