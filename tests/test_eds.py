""" Testing EDS file generation """

from durand import MinimalNode, Variable
from durand.datatypes import DatatypeEnum as DT

from .mock_network import MockNetwork
from .test_sdo import build_sdo_packet


def test_receiving_eds():
    network = MockNetwork()

    # create the node
    node = MinimalNode(network, node_id=2)

    # add a variable with index 0x2000 to the object dictionary of the node
    node.object_dictionary[0x2000] = Variable(DT.INTEGER16, "rw", value=5, minimum=0, maximum=10)
    node.object_dictionary[0x2001] = Variable(DT.INTEGER16, "rw", value=5)


    eds_content = node.eds.content.encode()

    network.receive(0x602, build_sdo_packet(cs=2, index=0x1021))  # init upload
    network.tx_mock.assert_called_with(
        0x582, b"\x41\x21\x10\x00" + len(eds_content).to_bytes(4, 'little')
    )  # response to init upload


    toggle_bit = 0

    while eds_content:
        network.receive(0x602, bytes([0x60 + (toggle_bit << 4)]) + b"\x21\x10\x00\x00\x00\x00\x00")  # request next segment
        if len(eds_content) <= 7:
            network.tx_mock.assert_called_with(
                0x582, bytes([(toggle_bit << 4) + 1 + ((7 - len(eds_content)) << 1)]) + eds_content[:7] + bytes(7 - len(eds_content))
            )
            return

        network.tx_mock.assert_called_with(
            0x582, bytes([toggle_bit << 4]) + eds_content[:7]
        )

        toggle_bit = not toggle_bit
        eds_content = eds_content[7:]


def test_eds_generation():
    network = MockNetwork()
    node = MinimalNode(network, node_id=2)

    assert "[Comments]" not in node.eds.content

    node.eds.comments = 'ABC\nDEF\n'
    assert node.eds.content.startswith("[Comments]\nLines=2\nLine1=ABC\nLine2=DEF\n\n")

