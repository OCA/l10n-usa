from odoo import models


class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    def _create_payment_vals_from_wizard(self, batch_result):
        payment_vals = super()._create_payment_vals_from_wizard(
            batch_result=batch_result
        )
        partner_bank_id = self._context.get("force_partner_bank_id")
        if partner_bank_id:
            payment_vals["partner_bank_id"] = partner_bank_id
        return payment_vals

    def _get_batches(self):
        batch_vals = super()._get_batches()
        partner_bank_id = self._context.get("force_partner_bank_id")
        if partner_bank_id:
            for vals in batch_vals:
                vals["partner_bank_id"] = partner_bank_id
        return batch_vals
