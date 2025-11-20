# Copyright 2025 Binhex.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class BillcomMfaWizard(models.TransientModel):
    _name = "billcom.mfa.wizard"
    _description = "Bill.com MFA Challenge Wizard"

    config_id = fields.Many2one(
        "billcom.config",
        string="Bill.com Configuration",
        required=True,
        readonly=True,
    )
    challenge_id = fields.Char(
        string="Challenge ID",
        readonly=True,
        help="Internal challenge ID from Bill.com",
    )
    session_id = fields.Char(
        string="Session ID",
        readonly=True,
        help="Temporary session ID for MFA validation",
    )
    mfa_code = fields.Char(
        string="MFA Code",
        size=6,
        help="6-digit code received via SMS or authenticator app",
    )
    state = fields.Selection(
        [
            ("challenge", "Waiting for Code"),
            ("validating", "Validating"),
            ("success", "Success"),
        ],
        default="challenge",
        readonly=True,
    )
    phone_number = fields.Char(
        readonly=True,
        help="Phone number where MFA code was sent",
    )

    def action_validate_mfa(self):
        """Validate MFA code and obtain Remember Me ID"""
        self.ensure_one()

        if not self.mfa_code or len(self.mfa_code) != 6:
            raise UserError(_("Please enter a valid 6-digit MFA code"))

        try:
            self.state = "validating"

            service = self.env["billcom.service"]
            remember_me_id = service.validate_mfa_challenge(
                self.config_id, self.challenge_id, self.session_id, self.mfa_code
            )

            if remember_me_id:
                # Store Remember Me ID in configuration
                self.config_id.sudo().write(
                    {
                        "mfa_remember_me_id": remember_me_id,
                        "mfa_device_name": self.config_id.mfa_device_name
                        or "Odoo Integration",
                    }
                )

                self.state = "success"

                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": _("MFA Setup Complete"),
                        "message": _(
                            "Remember Me ID has been saved successfully.\n"
                            "Payment creation is now enabled for 30 days.\n"
                            "You will need to renew MFA after 30 days."
                        ),
                        "type": "success",
                        "sticky": False,
                        "next": {"type": "ir.actions.act_window_close"},
                    },
                }

        except Exception as e:
            _logger.error(f"MFA validation failed: {e}")
            raise UserError(_(f"MFA validation failed: {e}")) from e

    def action_resend_code(self):
        """Resend MFA code"""
        self.ensure_one()

        try:
            service = self.env["billcom.service"]
            challenge_data = service.generate_mfa_challenge(
                self.config_id, self.session_id
            )

            self.write(
                {
                    "challenge_id": challenge_data["challenge_id"],
                    "phone_number": challenge_data.get("phone_number"),
                }
            )

            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Code Resent"),
                    "message": _("A new MFA code has been sent to your phone"),
                    "type": "info",
                },
            }

        except Exception as e:
            _logger.error(f"Failed to resend MFA code: {e}")
            raise UserError(_(f"Failed to resend code: {str(e)}")) from e
