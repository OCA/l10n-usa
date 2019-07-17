# Copyright 2017 Open Source Integrators <https://opensourceintegrators.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "US Form 1099",
    "version": "12.0.1.1.0",
    "author": "Open Source Integrators, Odoo Community Association (OCA)",
    "license": "AGPL-3",
    "summary": "Manage 1099 Types and Suppliers",
    "category": "Customers",
    "maintainer": "Open Source Integrators",
    "website": "https://github.com/OCA/l10n-usa",
    "depends": [
        "contacts",
        "account",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/type_1099_data.xml",
        "views/type_1099_view.xml",
        "views/res_partner.xml",
        "reports/account_payment_1099_report_views.xml",
    ],
    "installable": True,
}
