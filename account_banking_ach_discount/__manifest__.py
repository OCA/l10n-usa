# Copyright (C) 2019 Open Source Integrators
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Discount on ACH batch payments",
    "version": "14.0.1.0.0",
    "license": "AGPL-3",
    "author": "Open Source Integrators, Odoo Community Association (OCA)",
    "category": "Accounting",
    "maintainer": "Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/l10n-usa",
    "development_status": "Beta",
    "maintainers": ["bodedra"],
    "depends": [
        "account_payment_term_discount",
        "account_payment_batch_process",
        "account_payment_order",
        "account_banking_ach_credit_transfer",
        "account_banking_ach_direct_debit",
    ],
    "data": [
        "views/account_payment_view.xml",
    ],
}
