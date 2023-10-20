# Copyright (C) 2019 Open Source Integrators
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import models


class AccountMove(models.Model):
    _inherit = "account.move"

    def _compute_payments_widget_reconciled_info(self):
        res = super(AccountMove, self)._compute_payments_widget_reconciled_info()
        for move in self:
            if move.invoice_payments_widget:
                inv_number = move.name
                flag = False
                payment_lines = set()
                for line in move.line_ids:
                    payment_lines.update(
                        line.mapped("matched_credit_ids.credit_move_id.id")
                    )
                    payment_lines.update(
                        line.mapped("matched_debit_ids.debit_move_id.id")
                    )
                payment_move_line_ids = (
                    self.env["account.move.line"].browse(list(payment_lines)).sorted()
                )

                for mvl in payment_move_line_ids:
                    for item in move.invoice_payments_widget["content"]:
                        # get payment line
                        if mvl.payment_id.id == item["account_payment_id"]:
                            for pay_li in mvl.payment_id.line_ids.filtered(
                                lambda line: not line.reconciled
                            ):
                                # Get related payment line ref
                                if inv_number in pay_li.name:
                                    item["amount"] = abs(pay_li.amount_currency)
                        # for non-ach payment
                        # Deduct the discount only for the related payment.
                        # Discount is applied on the last payment (i.e. fully reconciled).
                        if (
                            mvl.payment_id
                            and mvl.move_id.id == self.id
                            and item["account_payment_id"] == mvl.payment_id.id
                        ):
                            if mvl.full_reconcile_id and not flag:
                                item["amount"] = item["amount"] - move.discount_taken
                                flag = True
        return res
