{
    "name": "Bill.com Integration",
    "summary": "Integration with Bill.com API v3 for vendor and bill synchronization",
    "author": "Binhex, Simple Solutions, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/l10n-usa",
    "license": "AGPL-3",
    "category": "Accounting",
    "version": "16.0.1.0.0",
    "depends": [
        "base",
        "web",
        "account",
        "contacts",
    ],
    "external_dependencies": {
        "python": ["requests", "PyJWT"],
    },
    "data": [
        "views/res_partner_views.xml",
        "views/billcom_config_views.xml",
        "views/account_move_views.xml",
        "views/account_payment_views.xml",
        "views/account_payment_register_views.xml",
        "views/account_payment_report.xml",
        "data/ir_cron_data.xml",
        "security/ir.model.access.csv",
        "security/billcom_security.xml",
    ],
    "demo": [],
    "assets": {
        "web.assets_backend": [
            "billcom/static/src/js/**/*",
        ],
    },
    "installable": True,
    "application": True,
}
