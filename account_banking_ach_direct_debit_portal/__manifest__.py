# Copyright 2025 Kencove (https://www.kencove.com)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

{
    "name": "Account Banking ACH Direct Debit Portal",
    "summary": "Account Banking ACH Direct Debit Portal",
    "version": "16.0.1.0.0",
    "license": "AGPL-3",
    "author": "Kencove, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/l10n-usa",
    "category": "Banking addons",
    "depends": ["account_banking_ach_direct_debit", "account_payment", "sale"],
    "data": [
        "data/ir_crons.xml",
        "data/res_config_settings_data.xml",
        "data/mail_template_data.xml",
        "security/portal_user_access.xml",
        "views/searchbar.xml",
        "views/autopay_rules_templates.xml",
        "views/banks_templates.xml",
        "views/breadcrumbs.xml",
        "views/homepage_templates.xml",
        "views/invoice_templates.xml",
        "views/payment_templates.xml",
        "views/portal_templates.xml",
        "views/payment_checkout_templates.xml",
        "views/alert_portal_templates.xml",
        "views/res_config_settings.xml",
        "views/res_user_views.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "account_banking_ach_direct_debit_portal/static/src/scss/*.scss",
            "account_banking_ach_direct_debit_portal/static/src/js/payment_form.js",
        ],
        "web.account_banking_ach_direct_debit_portal": [
            "account_banking_ach_direct_debit_portal/static/src/js/autopay_rules.js",
            "account_banking_ach_direct_debit_portal/static/src/js/invoice_table.js",
        ],
        "web.plaid_public": [
            "account_banking_ach_direct_debit_portal/static/src/js/add_bank_form.js",
        ],
    },
    "installable": True,
    "external_dependencies": {
        "python": ["ach", "plaid-python"],
    },
}
