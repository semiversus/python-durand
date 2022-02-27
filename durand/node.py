from .adapters import AdapterABC
from .object_dictionary import ObjectDictionary
from .services.sdo import SDOServer
from .services.pdo import TPDO, RPDO
from .services.nmt import NMTService, StateEnum
from .services.heartbeat import HeartbeatProducer
from .object_dictionary import Variable
from .datatypes import DatatypeEnum as DT


class Node:
    def __init__(self, adapter: AdapterABC, node_id: int,
                 od: ObjectDictionary = None):

        self.adapter = adapter
        self.node_id = node_id
        od = ObjectDictionary() if od is None else od
        self.object_dictionary = od

        self._subscriptions = dict()
        adapter.bind(self._subscriptions)

        self.nmt = NMTService(self)
        self.tpdo = {i: TPDO(self, i) for i in range(1, 5)}
        self.rpdo = {i: RPDO(self, i) for i in range(1, 5)}

        self.sdo_servers = {}
        self.add_sdo_server(0, 0x600 + self.node_id, 0x580 + self.node_id)
        
        HeartbeatProducer(self)
        
        od.add_object(Variable(0x1000, 0, DT.UNSIGNED32, 'ro', 0))  # device type
        od.add_object(Variable(0x1001, 0, DT.UNSIGNED8, 'ro', 0))  # error register
        od.add_object(Variable(0x1018, 1, DT.UNSIGNED32, 'ro', 0))  # identity - vendor-id
                
        self.nmt.set_state(StateEnum.PRE_OPERATIONAL)

    def add_sdo_server(self, index: int, cob_rx: int=None, cob_tx: int=None):
        assert index not in self.sdo_servers, f'Server {index} already added'
        self.sdo_servers[index] = SDOServer(self, index, cob_rx, cob_tx)

    def add_subscription(self, cob_id: int, callback):
        self._subscriptions[cob_id] = callback

    def remove_subscription(self, cob_id: int):
        self._subscriptions.pop(cob_id)
