from typing import List
from dataclasses import dataclass

from .adapters import AdapterABC
from .object_dictionary import ObjectDictionary
from .services.sdo import SDOServer
from .services.pdo import TPDO, RPDO
from .services.nmt import NMTService, StateEnum
from .services.lss import LSS
from .services.heartbeat import HeartbeatProducer
from .object_dictionary import Variable
from .datatypes import DatatypeEnum as DT


SDO_SERVERS = 127

@dataclass
class NodeCapabilities:
    sdo_servers: int
    rpdos: int
    tpdos: int


FullNodeCapabilities = NodeCapabilities(sdo_servers=128, rpdos=512, tpdos=512)


class Node:
    def __init__(self, adapter: AdapterABC, node_id: int, od: ObjectDictionary = None,
                 capabilities: NodeCapabilities = FullNodeCapabilities):

        self.adapter = adapter
        self.node_id = node_id
        od = ObjectDictionary() if od is None else od
        self.object_dictionary = od

        self.nmt = NMTService(self)

        self.tpdo = [TPDO(self, i) for i in range(capabilities.tpdos)]
        self.rpdo = [RPDO(self, i) for i in range(capabilities.rpdos)]

        self.sdo_servers: List[SDOServer] = list()

        assert (
            1 <= SDO_SERVERS <= 128
        ), "Number of SDO servers has to be between 1 and 128"

        for index in range(capabilities.sdo_servers):
            self.sdo_servers.append(SDOServer(self, index))

        self.heartbeat_producer = HeartbeatProducer(self)

        self.lss = LSS(self)

        od.add_object(Variable(0x1000, 0, DT.UNSIGNED32, "ro", 0))  # device type
        od.add_object(Variable(0x1001, 0, DT.UNSIGNED8, "ro", 0))  # error register

        # Identity object
        od.add_object(Variable(0x1018, 1, DT.UNSIGNED32, "ro", 0))  # vendor id
        od.add_object(Variable(0x1018, 2, DT.UNSIGNED32, "ro", 0))  # product code
        od.add_object(Variable(0x1018, 3, DT.UNSIGNED32, "ro", 0))  # revision number
        od.add_object(Variable(0x1018, 4, DT.UNSIGNED32, "ro", 0))  # serial number

        self.nmt.set_state(StateEnum.PRE_OPERATIONAL)


MinimalNodeCapabilities = NodeCapabilities(sdo_servers=1, rpdos=4, tpdos=4)


class MinimalNode(Node):
    def __init__(self, adapter: AdapterABC, node_id: int, od: ObjectDictionary = None):
        Node.__init__(self, adapter, node_id, od, MinimalNodeCapabilities)