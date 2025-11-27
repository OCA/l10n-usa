# Copyright 2025 Binhex - Simple Solutions
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    # Bill.com fields for payment registration
    is_sync_to_billcom = fields.Boolean(string="Sync to Bill.com", default=False)
    billcom_funding_account_type = fields.Selection(
        selection=[
            ("BANK_ACCOUNT", "Bank Account"),
            ("CARD_ACCOUNT", "Credit/Debit Card"),
            ("WALLET", "BILL Balance"),
            ("AP_CARD", "AP Card"),
        ],
        string="Funding Account Type",
        default="BANK_ACCOUNT",
        help="Type of funding account for Bill.com payment",
    )
    billcom_process_date = fields.Date(
        string="Process Date", default=fields.Date.context_today
    )
    billcom_pay_faster = fields.Boolean(
        string="Pay Faster",
        default=False,
        help="Enable Pay Faster for expedited payment delivery",
    )
    billcom_check_delivery_type = fields.Selection(
        selection=[
            ("STANDARD", "Standard"),
            ("RTP_DELIVERY", "Real-Time Payment (ACH)"),
            ("UPS_1DAY", "UPS 1-Day Delivery"),
            ("UPS_2DAY", "UPS 2-Days Delivery"),
            ("UPS_3DAY", "UPS 3-Days Delivery"),
            ("USPS_PRIORITY", "USPS Priority"),
        ],
        string="Check Delivery Type",
        default="STANDARD",
        help="Delivery method for check payments",
    )
    is_international_payment = fields.Boolean(
        string="International Payment",
        compute="_compute_is_international_payment",
        store=True,
    )

    @api.depends("partner_id", "partner_id.country_id")
    def _compute_is_international_payment(self):
        """Determine if payment is international based on vendor country"""
        company_country = self.env.company.country_id
        for wizard in self:
            if wizard.partner_id and wizard.partner_id.country_id:
                wizard.is_international_payment = (
                    wizard.partner_id.country_id.id != company_country.id
                )
            else:
                wizard.is_international_payment = False

    @api.model
    def default_get(self, fields_list):
        # Call to the original method
        res = super(AccountPaymentRegister, self).default_get(fields_list)

        # Only apply logic for vendor payments
        active_ids = self._context.get("active_ids") or []
        active_model = self._context.get("active_model")

        if active_model == "account.move" and active_ids:
            moves = self.env["account.move"].browse(active_ids)
            # Check if they are vendor invoices
            if moves and moves[0].move_type == "in_invoice":
                # Check if the vendor is configured to sync with Bill.com
                if moves[0].partner_id and hasattr(
                    moves[0].partner_id, "is_sync_to_billcom"
                ):
                    res["is_sync_to_billcom"] = moves[0].partner_id.is_sync_to_billcom

        return res

    def _create_payment_vals_from_wizard(self, batch_result):
        # Call to the original method
        payment_vals = super(
            AccountPaymentRegister, self
        )._create_payment_vals_from_wizard(batch_result)

        # Only apply logic for vendor payments
        if (
            payment_vals.get("partner_type") == "supplier"
            and payment_vals.get("payment_type") == "outbound"
        ):
            # Add Bill.com fields
            payment_vals.update(
                {
                    "is_sync_to_billcom": self.is_sync_to_billcom,
                    "billcom_funding_account_type": self.billcom_funding_account_type,
                    "billcom_process_date": self.billcom_process_date,
                    "billcom_pay_faster": self.billcom_pay_faster,
                    "billcom_check_delivery_type": self.billcom_check_delivery_type,
                }
            )

        return payment_vals

    def _create_payments(self):
        # Call to the original method to create payments
        payments = super()._create_payments()

        # If payments have been created and are configured to sync with Bill.com
        if payments:
            for payment in payments:
                # Only sync vendor payments
                if (
                    payment.partner_type == "supplier"
                    and payment.payment_type == "outbound"
                    and payment.is_sync_to_billcom
                ):
                    try:
                        # Try to sync the payment with Bill.com
                        payment.button_sync_to_billcom()
                    except Exception as e:
                        _logger.warning(
                            "Payment %s created but could not be synced to Bill.com: %s",
                            payment.name,
                            str(e),
                        )
                        # Set sync status to failed
                        payment.sudo().write(
                            {
                                "billcom_sync_status": "sync_failed",
                                "billcom_sync_error": str(e),
                            }
                        )
                        # Post warning to payment chatter
                        payment.message_post(
                            body=(
                                f"<p><strong>Bill.com Sync Warning</strong></p>"
                                f"<p>Payment created successfully but could not "
                                f"be synced to Bill.com.</p>"
                                f"<p><strong>Error:</strong></p>"  # noqa: E231
                                f"<pre>{str(e)}</pre>"
                                f"<p><em>You can manually sync this payment later "
                                f"from the payment form.</em></p>"
                            ),
                            message_type="notification",
                            subtype_xmlid="mail.mt_note",
                        )

        return payments
