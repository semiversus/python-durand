from .adapters import AdapterABC
from .object_dictionary import ObjectDictionary
from .services.sdo import SDOServer
from .services.pdo import TPDO, RPDO
from .services.nmt import NMTService
from .services.heartbeat import init_heartbeat


class Node:
    def __init__(self, adapter: AdapterABC, node_id: int,
                 od: ObjectDictionary = None):

        self.adapter = adapter
        self.node_id = node_id
        self.object_dictionary = ObjectDictionary() if od is None else od

        self.scheduler = Scheduler()

        self._subscriptions = dict()
        adapter.bind(self._subscriptions)

        self.nmt = NMTService(self)
        self.sdo = {0: SDOServer(self)}
        self.tpdo = {i: TPDO(self, i) for i in range(1, 5)}
        self.rpdo = {i: RPDO(self, i) for i in range(1, 5)}

        init_heartbeat(self)

    def add_sdo_servers(self, count: int):
        if len(self.sdo) > 1:
            raise ValueError('SDO servers already added')

        for index in range(1, count + 1):
            self.sdo[index] = SDOServer(self, index=index)

    def add_subscription(self, cob_id: int, callback):
        self._subscriptions[cob_id] = callback

    def remove_subscription(self, cob_id: int):
        self._subscriptions.pop(cob_id)
