from struct import Struct
from enum import IntEnum


class DatatypeEnum(IntEnum):
    BOOLEAN = 0x01
    INTEGER8 = 0x02
    INTEGER16 = 0x03
    INTEGER32 = 0x04
    INTEGER64 = 0x15
    UNSIGNED8 = 0x05
    UNSIGNED16 = 0x06
    UNSIGNED32 = 0x07
    UNSIGNED64 = 0x1B
    VISIBLE_STRING = 0x09
    OCTET_STRING = 0x0A
    REAL32 = 0x08
    REAL64 = 0x11
    DOMAIN = 0x0F


def is_numeric(datatype: DatatypeEnum):
    return datatype not in (
        DatatypeEnum.VISIBLE_STRING,
        DatatypeEnum.OCTET_STRING,
        DatatypeEnum.DOMAIN,
    )


def is_float(datatype: DatatypeEnum):
    return datatype in (DatatypeEnum.REAL32, DatatypeEnum.REAL64)


struct_dict = {
    DatatypeEnum.BOOLEAN: Struct("?"),
    DatatypeEnum.UNSIGNED8: Struct("B"),
    DatatypeEnum.INTEGER8: Struct("b"),
    DatatypeEnum.UNSIGNED16: Struct("<H"),
    DatatypeEnum.INTEGER16: Struct("<h"),
    DatatypeEnum.UNSIGNED32: Struct("<I"),
    DatatypeEnum.INTEGER32: Struct("<i"),
    DatatypeEnum.UNSIGNED64: Struct("<Q"),
    DatatypeEnum.INTEGER64: Struct("<q"),
    DatatypeEnum.REAL32: Struct("<f"),
    DatatypeEnum.REAL64: Struct("<d"),
    DatatypeEnum.VISIBLE_STRING: Struct("s"),
    DatatypeEnum.OCTET_STRING: Struct("s"),
    DatatypeEnum.DOMAIN: Struct("s"),
}
