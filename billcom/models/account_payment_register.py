import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    # Bill.com fields for payment registration
    is_sync_to_billcom = fields.Boolean(string="Sync to Bill.com", default=True)
    billcom_payment_type = fields.Selection(
        [
            ("ach", "ACH"),
            ("check", "Check"),
            ("virtual_card", "Virtual Card"),
            ("wire", "Wire Transfer"),
        ],
        string="Bill.com Payment Type",
        default="ach",
    )
    billcom_process_date = fields.Date(
        string="Process Date", default=fields.Date.context_today
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
                    "billcom_payment_type": self.billcom_payment_type,
                    "billcom_process_date": self.billcom_process_date,
                }
            )

        return payment_vals

    def _create_payments(self):
        # Call to the original method to create payments
        payments = super(AccountPaymentRegister, self)._create_payments()

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
                        _logger.error("Error syncing payment to Bill.com: %s", str(e))
                        # Show a message to the user but don't interrupt the process
                        self.env.user.notify_warning(
                            title=_("Bill.com Sync Warning"),
                            message=_(
                                "Payment created but could not be synced to Bill.com: %s"
                            )
                            % str(e),
                            sticky=True,
                        )

        return payments
