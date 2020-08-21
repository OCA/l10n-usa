# Copyright (C) 2020 Open Source Integrators
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "OnPay Connector",
    "version": "12.0.1.0.0",
    "license": "AGPL-3",
    "author": "Open Source Integrators, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/l10n-usa",
    "category": "Payroll",
    "depends": [
        "hr_timesheet_time_type",
        "hr_expense",
    ],
    "data": [
        "security/res_groups.xml",
        "security/ir.model.access.csv",
        "data/onpay_pay_type.xml",
        "views/project_time_type_view.xml",
        "views/hr_employee_view.xml",
        "views/product_product_view.xml",
        "wizards/onpay_data_export.xml",
        "views/hr_timesheet.xml",
    ],
    "auto_install": False,
    "application": False,
    "installable": True,
}
