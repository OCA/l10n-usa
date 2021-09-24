# Copyright (C) 2019 Open Source Integrators
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import models


class AccountMove(models.Model):
    _inherit = "account.move"

    def _get_reconciled_info_JSON_values(self):
        res = super(AccountMove, self)._get_reconciled_info_JSON_values()
        inv_number = self.ref
        if res:
            flag = False
            for item in res:
                payment_lines = set()
                for line in self.line_ids:
                    payment_lines.update(
                        line.mapped("matched_credit_ids.credit_move_id.id")
                    )
                    payment_lines.update(
                        line.mapped("matched_debit_ids.debit_move_id.id")
                    )
                    payment_move_line_ids = (
                        self.env["account.move.line"]
                        .browse(list(payment_lines))
                        .sorted()
                    )

                for mvl in payment_move_line_ids:
                    # get bank payment line
                    if mvl.move_id and mvl.id == item["payment_id"]:
                        for pay_li in mvl.bank_payment_line_id.payment_line_ids:
                            # Get related payment line ref
                            if pay_li.communication == inv_number:
                                item["amount"] = pay_li.amount_currency
                    # for non-ach payment
                    # Deduct the discount only for the related payment.
                    # Discount is applied on the last payment (i.e. fully reconciled).
                    if (
                        not mvl.bank_payment_line_id
                        and mvl.move_id.id == self.id
                        and item["account_payment_id"] == mvl.payment_id.id
                    ):
                        if mvl.full_reconcile_id and not flag:
                            item["amount"] = item["amount"] - self.discount_taken
                            flag = True

        return res

    def _prepare_discount_move_line(self, vals):
        valid = False
        for invoice in self:
            if (
                invoice.invoice_payment_term_id
                and invoice.invoice_payment_term_id.is_discount
                and invoice.invoice_payment_term_id.line_ids
            ):
                discount_information = (
                    invoice.invoice_payment_term_id._check_payment_term_discount(
                        invoice, invoice.date_invoice
                    )
                )
                discount_amt = discount_information[0]
                discount_account_id = discount_information[1]
                if discount_amt > 0.0:
                    vals.update(
                        {
                            "account_id": discount_account_id,
                            "move_id": invoice.id,
                            "bank_payment_line_id": False,
                            "name": "Early Pay Discount",
                        }
                    )
                    if invoice.type == "out_invoice":
                        vals.update({"credit": 0.0, "debit": discount_amt})
                        valid = True
                    elif invoice.type == "in_invoice":
                        vals.update({"credit": discount_amt, "debit": 0.0})
                        valid = True
            if valid:
                return vals
            else:
                return {}

    def _prepare_writeoff_move_line(self, payment_line, vals):
        for invoice in self:
            note = ""
            if payment_line.reason_code:
                note = payment_line.reason_code.display_name + ": "
            if payment_line.note:
                note += payment_line.note
            vals.update(
                {
                    "account_id": payment_line.writeoff_account_id.id,
                    "bank_payment_line_id": False,
                    "name": note,
                    "move_id": invoice.id,
                }
            )
            if invoice.move_type == "out_invoice":
                vals.update({"credit": 0.0, "debit": payment_line.payment_difference})
            elif invoice.move_type == "in_invoice":
                vals.update({"credit": payment_line.payment_difference, "debit": 0.0})
        return vals
