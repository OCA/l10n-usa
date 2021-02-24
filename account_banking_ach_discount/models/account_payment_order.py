# Copyright (C) 2019 Open Source Integrators
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models


class AccountPaymentOrder(models.Model):
    _inherit = "account.payment.order"

    def _prepare_move(self, bank_lines=None):
        values = super(AccountPaymentOrder, self)._prepare_move(bank_lines)
        bank_payment_line_pool = self.env["bank.payment.line"]
        line_ids = []
        for vals in values.get("line_ids"):
            # get the debit line for adjusting A/P entries
            if "bank_payment_line_id" in vals[2] and vals[2]["bank_payment_line_id"]:
                bank_payment_id = vals[2].get("bank_payment_line_id")
                bank_payment = bank_payment_line_pool.browse(bank_payment_id)
                for transaction in bank_payment.payment_line_ids:

                    temp_vals = vals[2].copy()
                    amount = transaction.amount_currency
                    discount = transaction.discount_amount
                    payment_difference = transaction.payment_difference
                    writeoff = (
                        payment_difference and payment_difference - discount or 0.0
                    )
                    invoice_close = transaction.payment_difference_handling != "open"
                    use_debit = transaction.move_id.move_type in (
                        "in_invoice",
                        "out_refund",
                    )

                    temp_vals["move_id"] = transaction.move_id.id
                    if use_debit:
                        temp_vals["debit"] = amount + discount
                    else:
                        temp_vals["credit"] = amount + discount

                    line_ids.append((0, 0, temp_vals))

                    if discount > 0:
                        discount_information = transaction.move_id.invoice_payment_term_id._check_payment_term_discount(
                            transaction.move_id, transaction.date
                        )
                        discount_vals = temp_vals.copy()
                        discount_vals["account_id"] = discount_information[1]
                        discount_vals["name"] = "Early Pay Discount"
                        if use_debit:
                            discount_vals["debit"] = 0.0
                            discount_vals["credit"] = discount_information[0]
                        else:
                            discount_vals["credit"] = 0.0
                            discount_vals["debit"] = discount_information[0]
                        discount_vals["bank_payment_line_id"] = False
                        if discount_vals:
                            line_ids.append((0, 0, discount_vals))

                    if invoice_close and round(writeoff, 2):
                        if use_debit:
                            temp_vals["debit"] = amount + discount + round(writeoff, 2)
                        else:
                            temp_vals["credit"] = amount + discount + round(writeoff, 2)
                        writeoff_vals = transaction.move_id._prepare_writeoff_move_line(
                            transaction, temp_vals.copy()
                        )
                        writeoff_vals["bank_payment_line_id"] = False
                        if writeoff_vals:
                            line_ids.append((0, 0, writeoff_vals))
            # payment order line
            else:
                line_ids.append(vals)

        values["line_ids"] = line_ids
        return values
