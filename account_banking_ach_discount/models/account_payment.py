# Copyright (C) 2019 Open Source Integrators
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountPayment(models.Model):
    _inherit = "account.payment"

    def action_validate_invoice_payment(self):
        # Check if Invoices have ACH IN/OUT payment method, to avoid any
        # conflict
        valid = False
        if self.filtered(lambda p: p.payment_method_id.code in ("ACH-In", "ACH-Out")):
            valid = True
            if any(len(record.invoice_ids) != 1 for record in self):
                # For multiple invoices, there is account.register.payments wizard
                raise UserError(
                    _(
                        "This method should only be called to process a "
                        "single invoice's payment."
                    )
                )
        if valid:
            for payment in self:
                payment_method = payment.payment_method_id
                if payment_method:
                    if payment_method.code in ("ACH-In", "ACH-Out"):
                        # Update invoice with Payment mode
                        if not payment.reconciled_invoice_ids.payment_mode_id:
                            payment_mode_id = self.env["account.payment.mode"].search(
                                [
                                    ("payment_type", "=", payment.payment_type),
                                    ("payment_method_id", "=", payment_method.id),
                                    ("payment_order_ok", "=", True),
                                ],
                                limit=1,
                            )
                            if payment_mode_id:
                                payment.reconciled_invoice_ids.write(
                                    {"payment_mode_id": payment_mode_id.id}
                                )
                                payment.reconciled_invoice_ids.move_id.line_ids.write(
                                    {"payment_mode_id": payment_mode_id.id}
                                )
                        action = (
                            payment.reconciled_invoice_ids.create_account_payment_line()
                        )
                        payment.unlink()
                        return action
        res = super(AccountPayment, self).action_validate_invoice_payment()
        return res


class AccountPaymentLine(models.Model):
    _inherit = "account.payment.line"

    discount_amount = fields.Monetary(currency_field="currency_id")
    total_amount = fields.Monetary(
        compute="_compute_total_amount", currency_field="currency_id"
    )
    payment_difference_handling = fields.Selection(
        [("open", "Keep open"), ("reconcile", "Mark invoice as fully paid")],
        default="reconcile",
        string="Action",
        copy=False,
    )
    writeoff_account_id = fields.Many2one(
        "account.account",
        string="Account",
        domain=[("deprecated", "!=", True)],
        copy=False,
    )
    reason_code = fields.Many2one("payment.adjustment.reason", string="Reason Code")
    note = fields.Text("Note")
    payment_difference = fields.Float(string="Payment Difference")
    move_id = fields.Many2one(
        "account.move", related="move_line_id.move_id", store=True
    )

    @api.onchange("discount_amount")
    def _onchange_discount_amount(self):
        if self.discount_amount:
            self.amount_currency = self.amount_currency - self.discount_amount

    @api.depends("amount_currency", "discount_amount")
    def _compute_total_amount(self):
        for line in self:
            line.total_amount = line.amount_currency + line.payment_difference

    @api.model
    def same_fields_payment_line_and_bank_payment_line(self):
        res = super(
            AccountPaymentLine, self
        ).same_fields_payment_line_and_bank_payment_line()
        res.append("discount_amount")
        return res
