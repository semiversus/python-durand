from typing import List

from .adapters import AdapterABC
from .object_dictionary import ObjectDictionary
from .services.sdo import SDOServer
from .services.pdo import TPDO, RPDO
from .services.nmt import NMTService, StateEnum
from .services.heartbeat import HeartbeatProducer
from .object_dictionary import Variable
from .datatypes import DatatypeEnum as DT


SDO_SERVERS = 127

class Node:
    def __init__(self, adapter: AdapterABC, node_id: int, od: ObjectDictionary = None):

        self.adapter = adapter
        self.node_id = node_id
        od = ObjectDictionary() if od is None else od
        self.object_dictionary = od

        self.nmt = NMTService(self)
        self.tpdo = {i: TPDO(self, i) for i in range(1, 5)}
        self.rpdo = {i: RPDO(self, i) for i in range(1, 5)}

        self.sdo_servers: List[SDOServer] = list()

        self.sdo_servers.append(
            SDOServer(self, 0, 0x600 + self.node_id, 0x580 + self.node_id)
        )

        assert 1 <= SDO_SERVERS <= 127, "Number of SDO servers has to be between 1 and 127"

        for index in range(1, SDO_SERVERS + 1):
            self.sdo_servers.append(SDOServer(self, index))

        HeartbeatProducer(self)

        od.add_object(Variable(0x1000, 0, DT.UNSIGNED32, "ro", 0))  # device type
        od.add_object(Variable(0x1001, 0, DT.UNSIGNED8, "ro", 0))  # error register
        od.add_object(
            Variable(0x1018, 1, DT.UNSIGNED32, "ro", 0)
        )  # identity - vendor-id

        self.nmt.set_state(StateEnum.PRE_OPERATIONAL)
