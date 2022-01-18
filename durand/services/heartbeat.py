from durand.node import Node
from durand.object_dictionary import Variable
from durand.datatypes import DatatypeEnum as DT


def init_heartbeat(node: Node):
    heartbeat_producer = Variable(0x1017, 0, DT.UNSIGNED16, 'rw')
    
    node.object_dictionary.add_update_callback(heartbeat_producer, self._update_heartbeat)
    node.object_dictionary.add_object(heartbeat_producer)