# Copyright 2026 Binhex - Edilio Escalona Almira.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
{
    "name": "US Sales Tax Engine - Branches",
    "version": "18.0.1.0.0",
    "category": "Accounting/Localizations",
    "summary": (
        "Origin-based sourcing from the company address and nexus "
        "inherited from parent companies for the US Sales Tax Engine."
    ),
    "author": "Binhex, Odoo Community Association (OCA)",
    "maintainers": ["edescalona", "crrodrigueztrujillo"],
    "website": "https://github.com/OCA/l10n-usa",
    "license": "LGPL-3",
    "development_status": "Alpha",
    "images": ["static/description/icon.png"],
    "depends": [
        "l10n_us_sales_tax_engine",
    ],
    "data": [
        "views/res_config_settings_views.xml",
        "views/sale_order_views.xml",
        "views/account_move_views.xml",
        "views/us_tax_calculation_log_views.xml",
    ],
    "pre_init_hook": "pre_init_hook",
}
