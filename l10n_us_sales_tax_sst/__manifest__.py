# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
{
    "name": "US Sales Tax — Streamlined (SST) Rate & Boundary",
    "version": "18.0.1.0.0",
    "category": "Accounting/Localizations",
    "summary": (
        "Import the Streamlined Sales Tax (SST) Rate & Boundary databases and "
        "resolve a US address to its FIPS jurisdictions and rates."
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
        "views/us_tax_boundary_views.xml",
        "views/us_tax_jurisdiction_views.xml",
        "wizards/sst_import_wizard_views.xml",
        "views/menus.xml",
    ],
}
