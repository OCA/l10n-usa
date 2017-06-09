# -*- coding: utf-8 -*-
# Copyright 2017 Ursa Information Systems <http://www.ursainfosystems.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "l10n_us_form_1099",
    "version": "10.0.1.0.0",
    "author": "Ursa Information Systems, Odoo Community Association (OCA)",
    "license": "AGPL-3",
    "summary": "Add 1099 field to res.partner that will auto-check supplier",
    "category": "Customers",
    "maintainer": "Ursa Information Systems",
    "website": "http://www.ursainfosystems.com",
    "depends": ["base"],
    "data": [
        "views/res_partner.xml",
    ],
    "qweb": [
    ],
    "installable": True,
}
