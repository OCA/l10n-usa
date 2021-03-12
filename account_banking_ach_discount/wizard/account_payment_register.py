# Copyright (C) 2019 Open Source Integrators
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import models


class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    def make_payments(self):
        if self.payment_method_id and self.payment_method_id.code in (
            "ACH-In",
            "ACH-Out",
        ):
            action = False
            payment_mode = self.env["account.payment.mode"].search(
                [
                    ("payment_type", "=", self.payment_type),
                    ("payment_method_id", "=", self.payment_method_id.id),
                    ("payment_order_ok", "=", True),
                ],
                limit=1,
            )
            payment_line_pool = self.env["account.payment.line"]
            # Update invoice with Payment mode
            if payment_mode:
                for line in self.invoice_payments:
                    invoice_id = line.invoice_id
                    # updated discount logic
                    discount = invoice_id.discount_taken
                    # discount should not be consider for open invoices
                    if line.payment_difference_handling != "open":
                        discount = invoice_id.discount_taken + line.payment_difference
                    invoice_id.write(
                        {
                            "payment_mode_id": payment_mode.id,
                            "discount_taken": discount,
                        }
                    )
                    invoice_id.line_ids.write({"payment_mode_id": payment_mode.id})
                    action = invoice_id.with_context(
                        payment_date=self.payment_date,
                        payment_line_state=line.payment_difference_handling,
                    ).create_account_payment_line()
                    # Find related ACH transaction line
                    domain = [("move_id", "=", invoice_id.id), ("state", "=", "draft")]
                    ach_lines = payment_line_pool.search(domain)
                    if ach_lines:
                        ach_lines.write(
                            {
                                "payment_difference_handling": line.payment_difference_handling,
                                "writeoff_account_id": line.writeoff_account_id.id,
                                "reason_code": line.reason_code.id,
                                "note": line.note,
                                "communication": "Payment of invoice %s"
                                % line.invoice_id.name,
                                "communication_type": "normal",
                                "amount_currency": line.amount,
                                "payment_difference": line.payment_difference,
                            }
                        )
                return action
        return super().make_payments()
