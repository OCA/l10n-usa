# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
{
    "name": "US Sales Tax — SST Simplified Electronic Return (SER)",
    "version": "18.0.1.0.0",
    "category": "Accounting/Localizations",
    "summary": (
        "Export a US sales tax return as the Streamlined Sales Tax (SST) "
        "Simplified Electronic Return (SER) XML for electronic filing."
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
        "views/res_config_settings_views.xml",
        "views/us_tax_jurisdiction_views.xml",
        "views/us_tax_return_views.xml",
    ],
    "demo": [
        "demo/us_tax_ser_demo.xml",
    ],
}
