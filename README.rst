================================================
Python Durand - CANopen Responder Device Library
================================================

A CANopen library to implement responder nodes.

**Backends:**

- CAN interfaces via python-can_

.. header

Synopsis
========

- Pure Python implementation
- Licensed under MIT (2021 Günther Jena)
- Source code hosted on GitHub.com_
- Tested on Python 3.7, 3.8, 3.9, and 3.10
- Unit tested with pytest_, coding style enforced with Black_, static type checking with mypy_, static code analysis with Pylint_, documentation generated with Sphinx_
- Supports CiA301_ (EN 50325-4)

.. _pytest: https://docs.pytest.org/en/latest
.. _Black: https://black.readthedocs.io/en/stable/
.. _mypy: http://mypy-lang.org/
.. _Pylint: https://www.pylint.org/
.. _Sphinx: http://www.sphinx-doc.org
.. _GitHub.com: https://github.com/semiversus/python-durand
.. _CiA301: http://can-cia.org/standardization/technical-documents

Feature List
============

* **Object Dictionary:**

  - Provides callbacks for validation, update, download, and read operations
  - Supports records, arrays, and variables

* **EDS Support:**

  - Dynamic generation of EDS files
  - Automatically provided via object 0x1021 ("Store EDS")

* **SDO Servers:**

  - Supports up to 128 SDO servers
  - Expedited, segmented, and block transfer for upload and download
  - Dynamically configurable COB-IDs
  - Custom upload and download handlers supported

* **PDO Support:**

  - Up to 512 TPDOs and 512 RPDOs
  - Dynamically configurable
  - Transmission types: synchronous (acyclic and every nth sync) and event-driven
  - Supports inhibit time

* **EMCY Producer Service:**

  - Dynamically configurable COB-ID
  - Supports inhibit time

* **Heartbeat Producer Service:**

  - Dynamically configurable

* **NMT Slave Service:**

  - Boot-up service
  - Callback for state change provided

* **SYNC Consumer Service:**

  - Dynamically configurable COB-ID
  - Callback for received sync provided

* **CiA305 Layer Setting Service:**

  - Supports fast scan
  - Configurable bitrate and node ID
  - Identify remote responder supported

* **CAN Interface Abstraction:**

  - Full support for python-can_
  - Automatic CAN ID filtering by subscribed services

* **Scheduling:**

  - Supports threaded and async operation

**TODO:**

- Build object dictionary via reading an EDS file
- Support MPDOs
- TIME consumer service
- Up- and download handler as I/O streams

Examples
========

**Creating a Node:**

.. code-block:: python

    import can
    from durand import CANBusNetwork, Node, Variable, Record, DatatypeEnum

    bus = can.Bus(bustype='socketcan', channel='vcan0')
    network = CANBusNetwork(bus)
    node = Node(network, node_id=0x01)

Congratulations! You now have a CiA-301 compliant node running. The Layer Setting Service is also supported out of the box.

**Adding Objects:**

.. code-block:: python

    od = node.object_dictionary

    # Add variable at index 0x2000
    od[0x2000] = Variable(DatatypeEnum.UNSIGNED16, access='rw', value=10, name='Parameter 1')

    # Add record at index 0x2001
    record = Record(name='Parameter Record')
    record[1] = Variable(DatatypeEnum.UNSIGNED8, access='ro', value=0, name='Parameter 2a')
    record[2] = Variable(DatatypeEnum.REAL32, access='rw', value=0, name='Parameter 2b')
    od[0x2001] = record

**Accessing Values:**

The objects can be read and written directly by accessing the object dictionary:

.. code-block:: python

    print(f'Value of Parameter 1: {od.read(0x2000, 0)}')
    od.write(0x2001, 1, value=0xAA)

**Adding Callbacks:**

A more event-driven approach is to use callbacks. The following callbacks are available:

- `validate_callbacks`: Called before a value in the object dictionary is updated
- `update_callbacks`: Called when the value has been changed (via `od.write` or via CAN bus)
- `download_callbacks`: Called when the value has been changed via CAN bus
- `read_callback`: Called when an object is read (return value is used)

.. code-block:: python

    od.validate_callbacks[(0x2000, 0)].add(lambda v: v % 2 == 0)
    od.update_callbacks[(0x2001, 2)].add(lambda v: print(f'Update for Parameter 2b: {v}'))
    od.download_callbacks[(0x2000, 0)].add(lambda v: print(f'Download for Parameter 1: {v}'))
    od.set_read_callback(0x2001, 1, lambda: 17)

**PDO Mapping:**

PDOs can be dynamically mapped via the SDO server or programmatically. The PDO indices start at 0.

.. code-block:: python

    node.tpdo[0].mapping = [(0x2001, 1), (0x2001, 2)]
    node.tpdo[0].transmission_type = 1  # Transmit on every SYNC

    node.rpdo[0].mapping = [(0x2000, 0)]
    node.tpdo[0].transmission_type = 255  # Event-driven (processed when received)

Installation
============

.. code-block:: bash

    pip install durand

Credits
=======

This library would not be possible without:

- python-canopen_: CANopen library (by Christian Sandberg)
- python-can_: CAN interface library (by Brian Thorne)

.. _python-canopen: https://github.com/christiansandberg/canopen
.. _python-can: https://github.com/hardbyte/python-can
