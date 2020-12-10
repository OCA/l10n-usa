from odoo import models


class AccountPaymentOrder(models.Model):
    _inherit = "account.payment.order"

    def generate_payment_file(self):
        """
        Creates the ACH Credit Transfer file by calling
        generate_ach_file in countinghouse_ach_base
        """
        self.ensure_one()
        if self.payment_method_id.code == "ACH-Out":
            return self.generate_ach_file()
        return super(AccountPaymentOrder, self).generate_payment_file()
