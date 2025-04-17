from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    enable_ach_payment_portal = fields.Boolean(
        string="Enable ACH Payment Portal",
        help="Allow this user to access ACH payment features on the portal.",
    )

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ["enable_ach_payment_portal"]

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + ["enable_ach_payment_portal"]

    @api.model
    def is_ach_portal_enabled_for_user(self):
        self.ensure_one()
        config_value = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "account_banking_ach_direct_debit_portal.enable_portal",
                default="selected_users_only",
            )
        )
        # Nobody is allowed to access
        if config_value == "disabled":
            return False
        elif config_value == "selected_users_only":
            return self.enable_ach_payment_portal
        elif config_value == "for_all_portal_users":
            return self.has_group("base.group_portal")
        else:
            return False
