# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
{
    "name": "US Sales Tax Engine",
    "version": "18.0.1.0.12",
    "category": "Accounting/Localizations",
    "summary": (
        "Hybrid USA Sales Tax engine: local DB first, "
        "external API fallback, full audit trail."
    ),
    "author": "Binhex, Odoo Community Association (OCA)",
    "maintainers": ["crrodrigueztrujillo"],
    "website": "https://github.com/OCA/l10n-usa",
    "license": "LGPL-3",
    "development_status": "Alpha",
    "depends": [
        "account",
        "sale_management",
        "mail",
    ],
    "data": [
        "security/us_tax_security.xml",
        "security/ir.model.access.csv",
        "data/us_tax_product_categories.xml",
        "data/us_tax_providers.xml",
        "data/ir_cron.xml",
        "views/res_config_settings_views.xml",
        "views/us_tax_jurisdiction_views.xml",
        "views/us_tax_zip_mapping_views.xml",
        "views/us_tax_rate_views.xml",
        "views/us_tax_product_category_views.xml",
        "views/us_tax_rule_views.xml",
        "views/us_tax_nexus_views.xml",
        "views/us_tax_provider_views.xml",
        "views/us_tax_api_cache_views.xml",
        "views/us_tax_calculation_log_views.xml",
        "views/us_tax_import_batch_views.xml",
        "views/product_template_views.xml",
        "views/sale_order_views.xml",
        "views/account_move_views.xml",
        "wizards/us_tax_import_wizard_views.xml",
        "views/menus.xml",
    ],
}
