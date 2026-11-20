# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
{
    "name": "US Sales Tax - Remittance & Reconciliation",
    "summary": "Book the DOR remittance vendor bill, post the collection "
    "allowance to income, reconcile the tax-payable accrual, tie out to GL",
    "version": "18.0.1.0.0",
    "license": "LGPL-3",
    "author": "Ledo Enterprises, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/l10n-usa",
    "category": "Localization",
    "maintainers": ["dnplkndll"],
    "development_status": "Alpha",
    "depends": ["l10n_us_sales_tax_state_returns", "account"],
    "data": [
        "security/ir.model.access.csv",
        "security/us_tax_authority_security.xml",
        "views/us_tax_authority_views.xml",
        "views/res_config_settings_views.xml",
        "views/us_tax_return_views.xml",
    ],
    "demo": [
        "demo/us_tax_remittance_demo.xml",
    ],
    "installable": True,
}
