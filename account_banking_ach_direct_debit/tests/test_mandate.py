# Copyright (C) 2021 - TODAY, Open Source Integrators
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestMandate(TransactionCase):
    def setUp(self):
        super(TestMandate, self).setUp()
        self.company = self.env.ref("base.main_company")

    def test_bank_mandate(self):
        bank_account = self.env.ref("account_payment_mode.res_partner_12_iban")
        mandate = self.env["account.banking.mandate"].create(
            {
                "partner_bank_id": bank_account.id,
                "signature_date": "2015-01-01",
                "company_id": self.company.id,
                "format": "ach",
                "type": "recurrent",
                "recurrent_sequence_type": "recurring",
            }
        )
        with self.assertRaises(ValidationError):
            mandate.recurrent_sequence_type = False
            mandate._check_recurring_type()
        mandate.format = "basic"
        mandate._achdd_mandate_set_state_to_expired()
        mandate._compute_display_name()
        mandate.validate()
        mandate.mandate_partner_bank_change()
        mandate._achdd_mandate_set_state_to_expired()
