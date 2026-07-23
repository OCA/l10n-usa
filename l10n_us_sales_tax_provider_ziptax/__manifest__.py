# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
{
    "name": "US Sales Tax Engine - ZipTax Provider",
    "version": "18.0.1.0.1",
    "category": "Accounting/Localizations",
    "summary": "ZipTax (zip.tax) provider plugin for the US Sales Tax Engine.",
    "author": "Binhex, Odoo Community Association (OCA)",
    "maintainers": ["crrodrigueztrujillo"],
    "website": "https://github.com/OCA/l10n-usa",
    "license": "LGPL-3",
    "development_status": "Alpha",
    "depends": [
        "l10n_us_sales_tax_engine",
    ],
    "data": [
        "data/us_tax_provider_ziptax.xml",
        "views/res_config_settings_views.xml",
    ],
}
