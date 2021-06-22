from durand.object_dictionary import ObjectDictionary
from durand.datatypes import DatatypeEnum
from durand import Node, Variable
from durand.adapters import CANAdapter


adapter = CANAdapter(interface='socketcan', channel='vcan0')

od = ObjectDictionary()
node = Node(adapter, 0x0E)

state_control = Variable(0x2000, 0, DatatypeEnum.UNSIGNED8, access='rw', default=0)
node.object_dictionary.add_object(state_control)

# change value
node.object_dictionary.write(state_control, 10)

# read value
node.object_dictionary.read(state_control)
node.tpdo[1].objects = (od.state_actual, od.common_errors, od.common_warnings)
node.tpdo[1].type = 'event'
node.tpdo[1].mutable = True

class MyObD:
    state_control = Variable(0x2000, 0, DatatypeEnum.UNSIGNED8, access='rw')

    @state_control.on_change
    def state_control(self, value):
        pass

    @state_control.on_read
    def state_control(self):
        return 0