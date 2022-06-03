import can
from durand import CANBusNetwork, Node, Variable, Record, DatatypeEnum

bus = can.Bus(bustype='socketcan', channel='vcan0')
network = CANBusNetwork(bus)

node = Node(network, node_id=0x01)

### Adding objects

od = node.object_dictionary

# add variable at index 0x2000
od[0x2000] = Variable(DatatypeEnum.UNSIGNED16, access='rw', value=10, name='Parameter 1')

# add record at index 0x2001
record = Record(name='Parameter Record')
record[1] = Variable(DatatypeEnum.UNSIGNED8, access='ro', value=0, name='Parameter 2a')
record[2] = Variable(DatatypeEnum.REAL32, access='rw', value=0, name='Parameter 2b')
od[0x2001] = record

### Set values
print(f'Value of Parameter 1: {od.read(0x2000, 0)}')
od.write(0x2001, 1, value=0xAA)

### Add callbacks
od.validate_callbacks[(0x2000, 0)].add(lambda v: v % 2 == 0)
od.update_callbacks[(0x2001, 2)].add(lambda v: print(f'Update for Parameter 2b: {v}'))
od.download_callbacks[(0x2000, 0)].add(lambda v: print(f'Download for Parmeter1: {v}'))
od.set_read_callback(0x2001, 1, lambda: 17)

### Map PDOs
node.tpdo[0].mapping = [(0x2001, 1), (0x2001, 2)]
node.tpdo[0].transmission_type = 1  # transmit on every SYNC

node.rpdo[0].mapping = [(0x2000, 0)]
node.tpdo[0].transmission_type = 255  # event driven (processed when received)
