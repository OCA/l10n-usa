# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
{
    "name": "US Sales Tax - State Returns (TX/FL/PA)",
    "summary": "Export a sales-tax return as a state-structured filing "
    "worksheet for non-SST states: Texas, Florida, Pennsylvania",
    "version": "18.0.1.0.0",
    "license": "LGPL-3",
    "author": "Ledo Enterprises, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/l10n-usa",
    "category": "Localization",
    "maintainers": ["dnplkndll"],
    "development_status": "Alpha",
    "depends": ["l10n_us_sales_tax_report"],
    "data": [
        "views/us_tax_return_views.xml",
    ],
    "installable": True,
}
