from odoo import models


class AccountPaymentRegister(models.TransientModel):
    _inherit = "payment.link.wizard"

    def _get_surcharge_percent(self):
        surcharge_parameter = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("account_banking_ach_direct_debit_portal.credit_card_surcharge")
        )

        try:
            return float(surcharge_parameter) if surcharge_parameter else 0.0
        except (TypeError, ValueError, OverflowError):
            return None

    def _get_additional_link_values(self):
        values = super()._get_additional_link_values()

        if self.res_model == "account.move":
            surcharge_percent = self._get_surcharge_percent()

            if surcharge_percent:
                surcharge_amount = self.amount * surcharge_percent / 100.0

                values = {
                    **values,
                    "amount": self.amount + surcharge_amount,
                    "surcharge_amount": surcharge_amount,
                    "base_total_amount": self.amount,
                }

                values["invoice"] = self.res_id
                del values["invoice_id"]

        return values
