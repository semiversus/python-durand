============================================
Python Durand - CANopen Slave Device Library
============================================

CANopen library to implement slave nodes.

Backends:

- CAN interfaces via python-can_

.. header

Synopsis
========

- Pure python implementation
- Under MIT license (2021 Günther Jena)
- Source is hosted on GitHub.com_
- Tested on Python 3.7, 3.8, 3.9 and 3.10
- Unit tested with pytest_, coding style checked with Flake8_, static type checked with mypy_, static code checked with Pylint_, documented with Sphinx_
- Supporting CiA301_ (EN 50325-4)

.. _pytest: https://docs.pytest.org/en/latest
.. _Flake8: http://flake8.pycqa.org/en/latest/
.. _mypy: http://mypy-lang.org/
.. _Pylint: https://www.pylint.org/
.. _Sphinx: http://www.sphinx-doc.org
.. _GitHub.com: https://github.com/semiversus/python-durand
.. _CiA301: http://can-cia.org/standardization/technical-documents

Feature List
============

* object dictionary
  * provides callbacks for *validation*, *update*, *download* and *read*
  * supports records, arrays and variables
* EDS support
  * dynamically generation of EDS file
  * automatically provided via object 0x1021 ("Store EDS")
* 128 SDO servers by default (can be reduced to 1)
  * expitited, segmented and block transfer for up- and download
  * COB-IDs dynamically configurable
  * custom up- and download handlers supported
* 512 TPDOs and 512 RPDOs by default (can be reduced to 0)
  * dynamically configurable
  * transmission types: synchronous (acyclic and every nth sync) and event driven
  * inhibit time supoorted
* EMCY service
  * COB-ID dynamically configurable
  * inhibit time supported
* Producer Heartbeat service
  * dynamically configurable
* NMT service
  * boot-up service
  * callback for state change provided
* SYNC (slave) service
  * COB-ID dynamically configurable
  * callback for received sync provided
* CiA305 Layer Setting Service
  * fast scan supported
  * baudrate and node id configuring supoorted
  * identify remote slave supported
* Scheduling supporting threaded and async operation

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
