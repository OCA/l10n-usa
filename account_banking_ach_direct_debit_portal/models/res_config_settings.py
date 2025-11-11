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
    surcharge_account_id = fields.Many2one(
        "account.account",
        string="Surcharge Account",
        domain="[('deprecated', '=', False), ('company_id', '=', company_id)]",
        help="Account to use for credit card surcharges.",
        related="company_id.surcharge_account_id",
        readonly=False,
    )
    discount_account_id = fields.Many2one(
        "account.account",
        string="Discount Account",
        domain="[('deprecated', '=', False), ('company_id', '=', company_id)]",
        help="Account to use for plaid discount.",
        related="company_id.discount_account_id",
        readonly=False,
    )
    charge_account_id = fields.Many2one(
        "account.account",
        string="Charge Account",
        domain="[('deprecated', '=', False), ('company_id', '=', company_id)]",
        help="Account to use for plaid charge.",
        related="company_id.charge_account_id",
        readonly=False,
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
    discount_journal_id = fields.Many2one(
        "account.journal",
        string="Discount Journal",
        help="Journal to use for plaid discount.",
        related="company_id.discount_journal_id",
        readonly=False,
    )

    unique_bank_account = fields.Boolean(
        help="Unique Bank Account",
        config_parameter="account_banking_ach_direct_debit_portal.unique_bank_account",
        default=False,
    )

    autopay_enrollment_template_id = fields.Many2one(
        "mail.template",
        string="Enrollment Email Template",
        config_parameter="account_banking_ach_direct_debit_portal."
        "autopay_enrollment_template_id",
        help="Email template sent to customers when they enroll for AutoPay. "
        "Leave empty to disable sending.",
    )

    autopay_enable_end_of_month = fields.Boolean(
        string="End Of Month",
        config_parameter="account_banking_ach_direct_debit_portal.autopay_enable_end_of_month",
    )

    autopay_enable_on_due_date = fields.Boolean(
        string="On Due Date",
        config_parameter="account_banking_ach_direct_debit_portal.autopay_enable_on_due_date",
    )
