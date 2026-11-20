# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
{
    "name": "US Sales Tax — Customer Exemption Certificates",
    "version": "18.0.1.1.0",
    "category": "Accounting/Localizations",
    "summary": (
        "Customer/entity sales-tax exemption certificates (resale, agriculture, "
        "government, …) that exempt a sale per customer, state and date."
    ),
    "author": "Ledo Enterprises, Odoo Community Association (OCA)",
    "maintainers": ["dnplkndll"],
    "website": "https://github.com/OCA/l10n-usa",
    "license": "LGPL-3",
    "development_status": "Alpha",
    "depends": [
        "l10n_us_sales_tax_engine",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/us_tax_exemption_reasons.xml",
        "data/ir_cron.xml",
        "views/us_tax_exemption_reason_views.xml",
        "views/us_tax_exemption_views.xml",
        "views/res_partner_views.xml",
        "views/account_fiscal_position_views.xml",
        "views/account_move_views.xml",
        "views/menus.xml",
    ],
    "demo": [
        "demo/us_tax_exemption_demo.xml",
    ],
}
