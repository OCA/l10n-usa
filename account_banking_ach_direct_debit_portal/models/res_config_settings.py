from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    plaid_env = fields.Selection(
        [
            ("sandbox", "Sandbox"),
            ("development", "Development"),
            ("production", "Production"),
        ],
        string="Plaid Environment",
        default="sandbox",
        help="Plaid environment to use (Sandbox, Development or Production).",
        config_parameter="account_banking_ach_direct_debit_portal.plaid_env",
    )

    plaid_client_id = fields.Char(
        "Client ID",
        help="Client ID provided by Plaid",
        config_parameter="account_banking_ach_direct_debit_portal.plaid_client_id",
    )

    plaid_secret = fields.Char(
        "Secret",
        help="Secret Key provided by Plaid",
        config_parameter="account_banking_ach_direct_debit_portal.plaid_secret",
    )

    credit_card_surcharge = fields.Float(
        string="Credit Card Surcharge (%)",
        config_parameter="account_banking_ach_direct_debit_portal.credit_card_surcharge",
        default=3.0,
        help="Surcharge percentage to apply "
        "when customers pay with a credit card on the portal.",
    )

    plaid_discount = fields.Float(
        string="Plaid Discount (%)",
        config_parameter="account_banking_ach_direct_debit_portal.plaid_discount",
        default=1.0,
        help="Plaid Discount to apply "
        "when customers pay with a bank account on the portal.",
    )

    enable_portal = fields.Selection(
        [
            ("disabled", "Disabled"),
            ("selected_users_only", "Selected Only User"),
            ("for_all_portal_users", "For All Portal Users"),
        ],
        default="selected_users_only",
        config_parameter="account_banking_ach_direct_debit_portal.enable_portal",
        help="Controls who can access the ACH Payment Portal features:\n"
        "- Disabled: Hide all ACH portal features\n"
        "- Selected Users Only: Show to users with 'Enable ACH Payment Portal' enabled\n"
        "- All Portal Users: Enable ACH features for all portal users",
    )
