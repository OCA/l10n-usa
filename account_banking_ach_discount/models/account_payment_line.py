# Copyright (C) 2019 Open Source Integrators
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import models


class AccountPaymentOrder(models.Model):
    _inherit = "account.payment.line"

    def _prepare_account_payment_vals(self):
        values = super()._prepare_account_payment_vals()
        note = ""
        if self.reason_code:
            note = self.reason_code.display_name + ": "
        if self.note:
            note += self.note
        payment_difference = self.payment_difference
        if self.payment_type == "outbound":
            payment_difference *= -1
        write_off_line_vals = {
            "account_id": self.writeoff_account_id.id,
            "name": note,
            "amount_currency": payment_difference,
            "balance": payment_difference,
        }
        values["write_off_line_vals"] = [write_off_line_vals]
        return values
