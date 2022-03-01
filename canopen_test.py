from operator import ne
import canopen

from durand import Node
from durand.adapters.canopen import CANOpenAdapter

network = canopen.Network()
network.connect(channel='vcan0', bustype='virtual')

adapter = CANOpenAdapter(network)
node = Node(adapter, 1)

od = canopen.ObjectDictionary()