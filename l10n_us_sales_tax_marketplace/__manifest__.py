# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
{
    "name": "US Sales Tax — Marketplace Facilitator",
    "version": "18.0.1.0.0",
    "category": "Accounting/Localizations",
    "summary": (
        "Mark orders/invoices collected & remitted by a marketplace facilitator "
        "(Amazon, eBay, …) so the seller does not also collect, and report them."
    ),
    "author": "Ledo Enterprises, Odoo Community Association (OCA)",
    "maintainers": ["dnplkndll"],
    "website": "https://github.com/OCA/l10n-usa",
    "license": "LGPL-3",
    "development_status": "Alpha",
    "depends": [
        "l10n_us_sales_tax_report",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/us_tax_marketplaces.xml",
        "views/us_tax_marketplace_views.xml",
        "views/sale_order_views.xml",
        "views/account_move_views.xml",
        "views/us_tax_return_views.xml",
        "views/menus.xml",
    ],
    "demo": [
        "demo/us_tax_marketplace_demo.xml",
    ],
}
