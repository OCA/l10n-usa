# -*- coding: utf-8 -*-
# Copyright 2017 Ursa Information Systems <http://www.ursainfosystems.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "US Accounting",
    "summary": "Additional features to manage US accounting in Odoo",
    "version": "10.0.0.0.2",
    "category": "Accounting",
    "website": "http://www.ursainfosystems.com",
    "author": "Ursa Information Systems, Odoo Community Association (OCA)",
    "license": "AGPL-3",
    "application": True,
    "installable": True,
    "depends": [
        "account_due_list",
        "account_payment_batch_process",
        "account_payment_credit_card",
        "account_reversal",
        "l10n_us",
        "l10n_us_check_writing_address",
        "l10n_us_form_1099",
        "partner_aging",
        "partner_daytopay",
    ],
}
