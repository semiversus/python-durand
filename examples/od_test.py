from durand.object_dictionary import Variable, ObjectDictionary
from durand.datatypes import DatatypeEnum as DT

# dynamic

od = ObjectDictionary()

state_control = Variable(0x2000, 0, DT.UNSIGNED8, 'rw')
state_actual = Variable(0x2001, 0, DT.UNSIGNED8, 'ro')


def update_state_control(value):
    print(f'Set control to {value}')


def read_state_actual():
    from random import randint
    return randint(0, 10)


od.add_object(state_control)
od.add_update_callback(state_control, update_state_control)

od.add_object(state_actual)
od.set_read_callback(state_actual, read_state_actual)

od.write(state_control, 5)
print(od.read(state_actual))