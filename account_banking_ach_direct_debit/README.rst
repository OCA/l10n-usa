.. image:: https://img.shields.io/badge/licence-AGPL--3-blue.svg
    :alt: License: AGPL-3

================================
Account Banking ACH Direct Debit
================================

Create ACH files for Direct Debit

Module to export direct debit payment orders in Nacha file format.


Installation
============

This module depends on :

* account_banking_mandate
* carta-ach
* stdnum


Configuration
=============

1. Your Company record must have the Legal ID specified.
2. Your Bank must have the Routing Number specified.


For defining a payment mode that uses ACH direct debit:

#. Go to *Accounting > Configuration > Management > Payment Modes*.
#. Create a Customer Invoice.
#. Select the Payment Method *ACH* (which is automatically created upon module installation).


Usage
=====

In the menu *Accounting > Payments > Debit Order*, create a new debit
order and select the Payment Mode dedicated to ACH Direct Debit that
you created during the configuration step.

Known issues / Roadmap
======================

 * Add support for EFT 1464 byte payment files required in Canada

Bug Tracker
===========

Bugs are tracked on `GitHub Issues
<https://github.com/thinkwelltwd/countinghouse>`_. In case of trouble, please
check there if your issue has already been reported. If you spotted it first,
help us smashing it by providing a detailed and welcomed feedback.
