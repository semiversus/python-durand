================================================
Python Durand - CANopen Responder Device Library
================================================

CANopen library to implement responder nodes.

Backends:

- CAN interfaces via python-can_

.. header

Synopsis
========

- Pure python implementation
- Under MIT license (2021 Günther Jena)
- Source is hosted on GitHub.com_
- Tested on Python 3.7, 3.8, 3.9 and 3.10
- Unit tested with pytest_, coding style done with Black_, static type checked with mypy_, static code checked with Pylint_, documented with Sphinx_
- Supporting CiA301_ (EN 50325-4)

.. _pytest: https://docs.pytest.org/en/latest
.. _Black: https://black.readthedocs.io/en/stable/
.. _mypy: http://mypy-lang.org/
.. _Pylint: https://www.pylint.org/
.. _Sphinx: http://www.sphinx-doc.org
.. _GitHub.com: https://github.com/semiversus/python-durand
.. _CiA301: http://can-cia.org/standardization/technical-documents

Feature List
============

* Object dictionary

  * provides callbacks for *validation*, *update*, *download* and *read*
  * supports records, arrays and variables

* EDS support

  * dynamically generation of EDS file
  * automatically provided via object 0x1021 ("Store EDS")

* up to 128 SDO servers

  * expetited, segmented and block transfer for up- and download
  * COB-IDs dynamically configurable
  * custom up- and download handlers supported

* up to 512 TPDOs and 512 RPDOs

  * dynamically configurable
  * transmission types: synchronous (acyclic and every nth sync) and event driven
  * inhibit time supported

* EMCY producer service

  * COB-ID dynamically configurable
  * inhibit time supported

* Heartbeat producer service

  * dynamically configurable

* NMT slave service

  * boot-up service
  * callback for state change provided

* SYNC consumer service

  * COB-ID dynamically configurable
  * callback for received sync provided

* CiA305 Layer Setting Service

  * fast scan supported
  * bitrate and node id configuring supported
  * identify remote responder supported

* CAN interface abstraction
  
  * python-can_ fully supported
  * automatic CAN id filtering by subscripted services

* Scheduling supporting threaded and async operation

TODO
  * build object dictionary via reading an EDS file
  * supporting MPDOs
  * TIME consumer service
  * Up- and download handler as io streams

Examples
========

Creating a node
---------------

.. code-block:: python

    import can
    from durand import CANBusNetwork, Node, Variable, Record, DatatypeEnum

    bus = can.Bus(bustype='socketcan', channel='vcan0')
    network = CANBusNetwork(bus)

    node = Node(network, node_id=0x01)

Congratulations! You have a CiA-301 compliant node running. Layer Setting Service is also supported out of the box.

Adding objects
--------------

.. code-block:: python

    od = node.object_dictionary

    # add variable at index 0x2000
    od[0x2000] = Variable(DatatypeEnum.UNSIGNED16, access='rw', value=10, name='Parameter 1')

    # add record at index 0x2001
    record = Record(name='Parameter Record')
    record[1] = Variable(DatatypeEnum.UNSIGNED8, access='ro', value=0, name='Parameter 2a')
    record[2] = Variable(DatatypeEnum.REAL32, access='rw', value=0, name='Parameter 2b')
    od[0x2001] = record

Access values
-------------

The objects can be read and written directly by accessing the object dictionary:

.. code-block:: python

    print(f'Value of Parameter 1: {od.read(0x2000, 0)}')
    od.write(0x2001, 1, value=0xAA)

Add callbacks
-------------

A more event driven approach is using of callbacks. Following callbacks are available:

* `validate_callbacks` - called before a value in the object dictionary is going to be updated
* `update_callbacks` - called when the value has been changed (via `od.write` or via CAN bus)
* `download_callbacks` - called when the value has been changed via CAN bus
* `read_callback` - called when a object is read (return value is used )

.. code-block:: python

    od.validate_callbacks[(0x2000, 0)].add(lambda v: v % 2 == 0)
    od.update_callbacks[(0x2001, 2)].add(lambda v: print(f'Update for Parameter 2b: {v}'))
    od.download_callbacks[(0x2000, 0)].add(lambda v: print(f'Download for Parmeter 1: {v}'))
    od.set_read_callback(0x2001, 1, lambda: 17)

PDO mapping
-----------

PDOs can dynamically mapped via the SDO server or programmatically. The PDO indices
start at 0.

.. code-block:: python

    node.tpdo[0].mapping = [(0x2001, 1), (0x2001, 2)]
    node.tpdo[0].transmission_type = 1  # transmit on every SYNC

    node.rpdo[0].mapping = [(0x2000, 0)]
    node.tpdo[0].transmission_type = 255  # event driven (processed when received)

Install
=======

.. code-block:: bash

    pip install durand

Credits
=======

This library would not be possible without:

* python-canopen_: CANopen library (by Christian Sandberg)
* python-can_: CAN interface library (by Brian Thorne)

.. _python-canopen: https://github.com/christiansandberg/canopen
.. _python-can: https://github.com/hardbyte/python-can
