import asyncio

from durand.object_dictionary import ObjectDictionary
from durand.datatypes import DatatypeEnum
from durand import Node, Variable
from durand.adapters.can import CANAdapter


adapter = CANAdapter(interface='socketcan', channel='vcan0', loop=asyncio.get_event_loop())

od = ObjectDictionary()
node = Node(adapter, 0x0E)

state_control = Variable(0x2000, 0, DatatypeEnum.UNSIGNED8, access='rw', default=0)
node.object_dictionary.add_object(state_control)

# change value
node.object_dictionary.write(state_control, 10)

# read value
node.object_dictionary.read(state_control)

asyncio.get_event_loop().run_forever()