# Copyright 2018-20 ForgeFlow S.L. (https://www.forgeflow.com)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl

{
    "name": "MIS Builder Templates for US Chart of Accounts",
    "author": "ForgeFlow, Odoo Community Association (OCA)",
    "maintainers": ["JordiBForgeFlow"],
    "website": "https://github.com/OCA/l10n-usa",
    "category": "Reporting",
    "version": "14.0.1.0.0",
    "license": "AGPL-3",
    "depends": ["mis_builder", "l10n_us_gaap"],  # In OCA/mis-builder
    "data": [
        "data/mis_report_styles.xml",
        "data/mis_report_balance_sheet.xml",
        "data/mis_report_income_statement.xml",
    ],
    "installable": True,
    "development_status": "Production/Stable",
}
