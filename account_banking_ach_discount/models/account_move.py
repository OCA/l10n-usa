# Copyright (C) 2019 Open Source Integrators
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import api, models


class AccountMove(models.Model):
    _inherit = "account.move"

    @api.depends()
    def _compute_payments_widget_reconciled_info(self):
        res = super()._compute_payments_widget_reconciled_info()
        for move in self:
            widget_data = move.invoice_payments_widget
            if not widget_data:
                continue
            inv_number = move.name
            discount_applied = False
            matched_lines = move.line_ids
            credit_lines = matched_lines.mapped("matched_credit_ids.credit_move_id")
            debit_lines = matched_lines.mapped("matched_debit_ids.debit_move_id")
            payment_lines = credit_lines | debit_lines
            for payment_line in payment_lines:
                # get payment line
                payment = payment_line.payment_id
                if not payment:
                    continue
                for item in widget_data["content"]:
                    if item.get("account_payment_id") != payment.id:
                        continue
                    payment_move = payment.move_id
                    for pay_li in payment_move.line_ids.filtered(
                        lambda line: not line.reconciled
                    ):
                        # Get related payment line ref
                        if inv_number in pay_li.name:
                            item["amount"] = abs(pay_li.amount_currency)
                    # for non-ach payment
                    # Deduct the discount only for the related payment.
                    # Discount is applied on the last payment (i.e. fully reconciled).
                    if (
                        payment_move.id == move.id
                        and payment_line.full_reconcile_id
                        and not discount_applied
                    ):
                        item["amount"] = item["amount"] - move.discount_taken
                        discount_applied = True
        return res
