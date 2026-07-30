# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
{
    "name": "US Sales Tax Reporting",
    "version": "18.0.1.0.0",
    "category": "Accounting/Localizations",
    "summary": (
        "Per-jurisdiction sales tax returns from collected tax: state, "
        "county, city and special-district breakdown for filing."
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
        "views/us_tax_return_views.xml",
        "views/menus.xml",
    ],
}
