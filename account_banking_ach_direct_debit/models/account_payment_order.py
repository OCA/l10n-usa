# Copyright 2018 Thinkwell Designs <dave@thinkwelldesigns.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import _, models


class AccountPaymentOrder(models.Model):
    _inherit = "account.payment.order"

    def generate_payment_file(self):
        """
        Creates the ACH Direct Debit file by calling
        generate_ach_file in countinghouse_ach_base
        """
        self.ensure_one()
        if self.payment_method_id.code == "ACH-In":
            return self.generate_ach_file()
        return super(AccountPaymentOrder, self).generate_payment_file()

    def generated2uploaded(self):
        """Write 'last debit date' on mandates
        Set mandates from first to recurring
        Set oneoff mandates to expired
        """
        # I call super() BEFORE updating the sequence_type
        # from first to recurring, so that the account move
        # is generated BEFORE, which will allow the split
        # of the account move per sequence_type
        res = super(AccountPaymentOrder, self).generated2uploaded()
        mandate = self.env["account.banking.mandate"]
        for order in self:
            to_expire_mandates = first_mandates = all_mandates = mandate
            for payment in order.payment_ids:
                if payment.mandate_id in all_mandates:
                    continue
                all_mandates += payment.mandate_id
                if payment.mandate_id.type == "oneoff":
                    to_expire_mandates += payment.mandate_id
                elif payment.mandate_id.type == "recurrent":
                    seq_type = payment.mandate_id.recurrent_sequence_type
                    if seq_type == "final":
                        to_expire_mandates += payment.mandate_id
                    elif seq_type == "first":
                        first_mandates += payment.mandate_id
            all_mandates.write({"last_debit_date": order.date_generated})
            to_expire_mandates.write({"state": "expired"})
            first_mandates.write({"recurrent_sequence_type": "recurring"})
            for first_mandate in first_mandates:
                first_mandate.message_post(
                    body=_(
                        "Automatically switched from <b>First</b> to "
                        "<b>Recurring</b> when the debit order "
                        "<a href=# data-oe-model=account.payment.order "
                        "data-oe-id=%(order_id)d>%(order_name)s</a> "
                        "has been marked as uploaded."
                    )
                    % {"order_id": order.id, "order_name": order.name}
                )
        return res
