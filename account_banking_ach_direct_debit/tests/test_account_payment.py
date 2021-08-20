# Copyright (C) 2021 - TODAY, Open Source Integrators
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)
from datetime import datetime

from odoo.tests.common import TransactionCase


class TestPayment(TransactionCase):
    def setUp(self):
        super(TestPayment, self).setUp()
        self.partner = self.env["res.partner"].create({"name": "Partner 1"})
        self.company = self.env.ref("base.main_company")
        self.company.partner_id = self.partner.id
        self.company.legal_id_number = "12-3456789"
        self.payment_method_model = self.env["account.payment.method"]
        self.ach_payment_method_01 = self.payment_method_model.search(
            [("code", "=", "ACH-In")], limit=1
        )
        self.acme_bank = self.env["res.bank"].create(
            {
                "name": "ACME Bank",
                "bic": "GEBABEBB03B",
                "city": "Charleroi",
                "routing_number": "021000021",
                "country": self.env.ref("base.be").id,
            }
        )
        bank_account = self.env["res.partner.bank"].create(
            {
                "acc_number": "0023032234211123",
                "partner_id": self.partner.id,
                "bank_id": self.acme_bank.id,
                "company_id": self.company.id,
            }
        )
        self.journal_c1 = self.env["account.journal"].create(
            {
                "name": "Journal 1",
                "code": "J1",
                "type": "bank",
                "company_id": self.company.id,
                "bank_account_id": bank_account.id,
            }
        )
        self.inbound_mode = self.env.ref(
            "account_payment_mode.payment_mode_inbound_dd1"
        )
        self.journal = self.env["account.journal"].search(
            [("type", "=", "bank"), ("company_id", "=", self.env.user.company_id.id)],
            limit=1,
        )
        self.payment_mode_c1 = self.env["account.payment.mode"].create(
            {
                "name": "ACH Direct Debit",
                "bank_account_link": "variable",
                "payment_method_id": self.ach_payment_method_01.id,
                "company_id": self.company.id,
                "fixed_journal_id": self.journal_c1.id,
                "variable_journal_ids": [(6, 0, [self.journal_c1.id])],
            }
        )

    def test_account_payment_order(self):
        self.payment_order = self.env["account.payment.order"].create(
            {
                "payment_type": "inbound",
                "payment_mode_id": self.payment_mode_c1.id,
                "journal_id": self.journal_c1.id,
                "payment_method_id": self.ach_payment_method_01.id,
            }
        )
        self.payment_order.generate_payment_file()
        line_created_due = (
            self.env["account.payment.line.create"]
            .with_context(
                active_model="account.payment.order", active_id=self.payment_order.id
            )
            .create({"date_type": "due", "due_date": datetime.now()})
        )
        line_created_due.payment_mode = "any"
        line_created_due.target_move = "all"
        line_created_due.allow_blocked = True
        line_created_due.populate()
        line_created_due.create_payment_lines()
        self.payment_order.draft2open()
        self.payment_order.generated2uploaded()
