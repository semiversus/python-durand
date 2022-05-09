from typing import List
from dataclasses import dataclass

from .adapters import AdapterABC
from .object_dictionary import ObjectDictionary
from .services.sdo import SDOServer
from .services.pdo import TPDO, RPDO
from .services.nmt import NMTService, StateEnum
from .services.lss import LSS
from .services.sync import Sync
from .services.emcy import EMCY
from .services.heartbeat import HeartbeatProducer
from .object_dictionary import Variable, Record
from .datatypes import DatatypeEnum as DT


SDO_SERVERS = 127


@dataclass
class NodeCapabilities:
    sdo_servers: int
    rpdos: int
    tpdos: int


FullNodeCapabilities = NodeCapabilities(sdo_servers=128, rpdos=512, tpdos=512)


class Node:
    def __init__(
        self,
        adapter: AdapterABC,
        node_id: int,
        od: ObjectDictionary = None,
        capabilities: NodeCapabilities = FullNodeCapabilities,
    ):

        self.adapter = adapter
        self.node_id = node_id
        od = ObjectDictionary() if od is None else od
        self.object_dictionary = od

        self.nmt = NMTService(self)
        self.sync = Sync(self)

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
        self.emcy = EMCY(self)

        od[0x1000] = Variable(DT.UNSIGNED32, "ro", 0)  # device type

        od[0x1008] = Variable(DT.VISIBLE_STRING, "ro", b"")  # manufacturer device name
        od[0x1009] = Variable(DT.VISIBLE_STRING, "ro", b"")  # manufacturer hardware version
        od[0x100A] = Variable(DT.VISIBLE_STRING, "ro", b"")  # manufacturer software version

        # Identity object
        identity_record = Record()
        identity_record[1] = Variable(DT.UNSIGNED32, "ro", 0)  # vendor id
        identity_record[2] = Variable(DT.UNSIGNED32, "ro", 0)  # product code
        identity_record[3] = Variable(DT.UNSIGNED32, "ro", 0)  # revision number
        identity_record[4] = Variable(DT.UNSIGNED32, "ro", 0)  # serial number

        od[0x1018] = identity_record
        self.nmt.set_state(StateEnum.PRE_OPERATIONAL)


MinimalNodeCapabilities = NodeCapabilities(sdo_servers=1, rpdos=4, tpdos=4)


class MinimalNode(Node):
    def __init__(self, adapter: AdapterABC, node_id: int, od: ObjectDictionary = None):
        Node.__init__(self, adapter, node_id, od, MinimalNodeCapabilities)
