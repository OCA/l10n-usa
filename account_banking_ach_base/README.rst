.. image:: https://img.shields.io/badge/licence-AGPL--3-blue.svg
    :alt: License: AGPL-3

=======================
Counting House ACH Base
=======================

Add fields to Bank, Partner and Company required for ACH transactions in USA.

Installation
============

This module depends on :

* stdnum


Usage
=====

Add `routing_number` on Bank records.

Add Legal ID on Partner and Company records.

Add Mandate URL field to Company record. Use in email templates to provide customer with an easy
way to access your Mandate Authorization form to streamline ACH authorizations.

Known issues / Roadmap
======================

 * Add support for EFT 1464 byte payment files required in Canada

Bug Tracker
===========

Bugs are tracked on `GitHub Issues
<https://github.com/thinkwelltwd/countinghouse>`_. In case of trouble, please
check there if your issue has already been reported. If you spotted it first,
help us smashing it by providing a detailed and welcomed feedback.
