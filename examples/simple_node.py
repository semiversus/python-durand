import asyncio

from durand.object_dictionary import ObjectDictionary
from durand.datatypes import DatatypeEnum
from durand import MinimalNode, Variable
from durand.adapters.can import CANAdapter


adapter = CANAdapter(interface='socketcan', channel='can0', loop=asyncio.get_event_loop())

node = MinimalNode(adapter, 0x20)

state_control = Variable(DatatypeEnum.UNSIGNED8, access='rw', value=0)
node.object_dictionary[0x2000] = state_control

node.tpdo[1].mapping = ((0x2000, 0),)
node.rpdo[1].mapping = ((0x2000, 0),)

# change value
node.object_dictionary.write(0x2000, 0, 10)

# read value
node.object_dictionary.read(0x2000, 0)
asyncio.get_event_loop().call_later(2, node.object_dictionary.write, 0x2000, 0, 11)

data_var = Variable(DatatypeEnum.DOMAIN, access='rw')
node.object_dictionary[0x2001] = data_var

node.object_dictionary.update_callbacks[(0x2001, 0)].add(print)

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
def download_callback(node, index, subindex, size):
    if index == 0x2001:
        return MyDownloadHandler()

    return None

node.sdo_servers[0].download_manager.set_handler_callback(download_callback)

def change_baudrate(baudrate: int):
    print('CHANGE BAUDRATE', baudrate)

node.lss.set_baudrate_change_callback(change_baudrate)

asyncio.get_event_loop().run_forever()