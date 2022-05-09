import asyncio

from durand.object_dictionary import ObjectDictionary
from durand.datatypes import DatatypeEnum
from durand import MinimalNode, Variable
from durand.adapters.can import CANAdapter


adapter = CANAdapter(interface='socketcan', channel='vcan0', loop=asyncio.get_event_loop())

node = MinimalNode(adapter, 0x0E)

state_control = Variable(0x2000, 0, DatatypeEnum.UNSIGNED8, access='rw', default=0)
node.object_dictionary.add_object(state_control)

node.tpdo[1].map_objects(state_control)
node.rpdo[1].map_objects(state_control)

# change value
node.object_dictionary.write(state_control, 10)

# read value
node.object_dictionary.read(state_control)
asyncio.get_event_loop().call_later(2, node.object_dictionary.write, state_control, 11)

data_var = Variable(0x2001, 0, DatatypeEnum.DOMAIN, access='rw')
node.object_dictionary.add_object(data_var)

node.object_dictionary.update_callbacks[data_var].add(print)

class MyDownloadHandler:
    def __init__(self):
        self._file = open('update.bin', 'wb')

    def on_receive(self, data: bytes):
        self._file.write(data)

    def on_finish(self):
        self._file.close()

    def on_abort(self):
        self._file.close()

#define handler
def download_callback(node, variable, size):
    if variable.index == 0x2001:
        return MyDownloadHandler()

    return None

node.sdo_servers[0].download_manager.set_handler_callback(download_callback)

def change_baudrate(baudrate: int):
    print('CHANGE BAUDRATE', baudrate)

node.lss.set_baudrate_change_callback(change_baudrate)

asyncio.get_event_loop().run_forever()