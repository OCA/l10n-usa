# Copyright (C) 2021 - TODAY, Open Source Integrators
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)
from odoo import fields

from odoo.addons.base.tests.common import BaseCommon


class TestPayment(BaseCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company.partner_id = cls.partner.id
        cls.company.legal_id_number = "12-3456789"
        cls.payment_method_model = cls.env["account.payment.method"]
        cls.ach_payment_method_01 = cls.payment_method_model.search(
            [("code", "=", "ACH-In")], limit=1
        )
        cls.acme_bank = cls.env["res.bank"].create(
            {
                "name": "ACME Bank",
                "bic": "GEBABEBB03B",
                "city": "Charleroi",
                "routing_number": "021000021",
                "country": cls.env.ref("base.be").id,
            }
        )
        bank_account = cls.env["res.partner.bank"].create(
            {
                "acc_number": "0023032234211123",
                "partner_id": cls.partner.id,
                "bank_id": cls.acme_bank.id,
                "company_id": cls.company.id,
            }
        )
        cls.journal_c1 = cls.env["account.journal"].create(
            {
                "name": "Journal 1",
                "code": "J1",
                "type": "bank",
                "company_id": cls.company.id,
                "bank_account_id": bank_account.id,
            }
        )
        cls.inbound_mode = cls.env.ref("account_payment_mode.payment_mode_inbound_dd1")
        cls.journal = cls.env["account.journal"].search(
            [("type", "=", "bank"), ("company_id", "=", cls.company.id)],
            limit=1,
        )
        cls.payment_mode_c1 = cls.env["account.payment.mode"].create(
            {
                "name": "ACH Direct Debit",
                "bank_account_link": "variable",
                "payment_method_id": cls.ach_payment_method_01.id,
                "company_id": cls.company.id,
                "fixed_journal_id": cls.journal_c1.id,
                "variable_journal_ids": [(6, 0, [cls.journal_c1.id])],
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
        line_created_due = (
            self.env["account.payment.line.create"]
            .with_context(
                active_model="account.payment.order", active_id=self.payment_order.id
            )
            .create(
                {
                    "date_type": "due",
                    "due_on": "<=",
                    "filter_date": fields.Date.today(),
                    "payment_mode": "any",
                    "target_move": "all",
                }
            )
        )
        line_created_due.populate()
        self.assertGreater(
            len(line_created_due.move_line_ids),
            1,
            "Expected more than one move line before filtering",
        )
        line_created_due.move_line_ids = line_created_due.move_line_ids.filtered(
            lambda line: line.journal_id and line.journal_id.type == "general"
        )  # copy from: https://github.com/odoo/odoo/commit/67dc715#diff-78f3e1847de8ca0acf28d72a412947a549acdb08142d1dadf7646363d7972cb0L478
        self.assertEqual(len(line_created_due.move_line_ids), 1)
        line_created_due.create_payment_lines()
        self.payment_order.draft2open()
        self.payment_order.generated2uploaded()
