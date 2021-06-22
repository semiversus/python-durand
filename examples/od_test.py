from durand.object_dictionary import Variable, ObjectDictionary
from durand.datatypes import DatatypeEnum as DT

# static example

class IcarusOD(ObjectDictionary):
    state_control = Variable(0x2000, 0, DT.UNSIGNED8, 'rw')
    state_actual = Variable(0x2001, 0, DT.UNSIGNED8, 'ro')

    @state_control.on_update
    def update_state_control(self, value):
        print(f'Set control to {value}')

    @state_actual.on_read
    def read_state_actual(self):
        from random import randint
        return randint(0, 10)

od = IcarusOD()

od.write(od.state_control, 5)
print(od.read(od.state_actual))


# dynamic

od = ObjectDictionary()

state_control = Variable(0x2000, 0, DT.UNSIGNED8, 'rw')
state_actual = Variable(0x2001, 0, DT.UNSIGNED8, 'ro')

od.add_object(state_control)
od.add_object(state_actual)

@state_control.on_update(od)
def update_state_control(value):
    print(f'Set control to {value}')

@state_actual.on_read(od)
def read_state_actual():
    from random import randint
    return randint(0, 10)

od.write(state_control, 5)
print(od.read(state_actual))