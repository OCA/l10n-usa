# Copyright (C) 2019 Open Source Integrators
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def _prepare_payment_line_vals(self, payment_order):
        vals = super(AccountMoveLine, self)._prepare_payment_line_vals(payment_order)
        invoice = self.move_id
        amount_currency = vals.get("amount_currency")
        # No discount for open invoices
        if (
            (
                "payment_line_state" in self._context
                and self._context.get("payment_line_state") != "open"
            )
            or self._context.get("is_new_order")
            or self._context.get("is_update_order")
        ):
            if (
                invoice
                and invoice.invoice_payment_term_id
                and invoice.invoice_payment_term_id.is_discount
                and invoice.invoice_payment_term_id.line_ids
            ):
                discount_information = (
                    invoice.invoice_payment_term_id._check_payment_term_discount(
                        invoice,
                        self._context.get("payment_date") or invoice.invoice_date,
                    )
                )
                discount_amt = discount_information[0]
                vals.update(
                    {
                        "discount_amount": discount_amt,
                        "amount_currency": amount_currency - discount_amt,
                        "writeoff_account_id": discount_information[1],
                    }
                )
        return vals
