# Copyright 2017 Open Source Integrators <https://opensourceintegrators.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "US Form 1099",
    "version": "12.0.1.0.0",
    "author": "Open Source Integrators, Odoo Community Association (OCA)",
    "license": "AGPL-3",
    "summary": "Add 1099 field to res.partner that will auto-check supplier",
    "category": "Customers",
    "maintainer": "Open Source Integrators",
    "website": "https://github.com/OCA/l10n-usa",
    "depends": [
        "contacts"
    ],
    "data": [
        "views/res_partner.xml",
    ],
    "installable": True,
}
