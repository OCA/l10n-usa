.. image:: https://img.shields.io/badge/license-AGPL--3-blue.png
   :target: https://www.gnu.org/licenses/agpl
   :alt: License: AGPL-3

======================================================
United States Basic GAAP Chart of Accounts MIS Reports
======================================================

Includes the following templates for the *mis_builder* module.

* US Balance Sheet
* US Income Statement

The templates are based on the Chart of Accounts provided by the module
*l10n_us_gaap*.

This module contains in the 'docs' folder a sample Income Statement and
Balance Sheet with the full drill down to individual accounts.


Installation
============

This module depends on:

* The module *mis_builder* that can be obtained in
  https://apps.odoo.com, or https://github.com/OCA/mis-builder.


Configuration
=============

* Go to *Invoicing > Reporting > MIS Reports* and create a new report,
  indicating the required periods, and using one of the templates provided
  by this module.

If you create new accounts, make sure that they fall into the right account
group, and they will then be displayed correctly in the MIS Reports.

.. image:: https://odoo-community.org/website/image/ir.attachment/5784_f2813bd/datas
   :alt: Try me on Runbot
   :target: https://runbot.odoo-community.org/runbot/119/12.0

Bug Tracker
===========

Bugs are tracked on `GitHub Issues
<https://github.com/OCA/l10n-usa/issues>`_. In case of trouble, please
check there if your issue has already been reported. If you spotted it first,
help us smash it by providing detailed and welcomed feedback.

Credits
=======

Contributors
------------

* Eficent Business and IT Consulting Services, S.L. <https://www.eficent.com>

  * Jordi Ballester Alomar <jordi.ballester@eficent.com>
  * Miquel Raïch <miquel.raich@eficent.com>

Maintainer
----------

.. image:: https://odoo-community.org/logo.png
   :alt: Odoo Community Association
   :target: https://odoo-community.org

This module is maintained by the OCA.

OCA, or the Odoo Community Association, is a nonprofit organization whose
mission is to support the collaborative development of Odoo features and
promote its widespread use.

To contribute to this module, please visit https://odoo-community.org.
