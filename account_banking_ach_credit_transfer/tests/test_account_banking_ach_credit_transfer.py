# Copyright (C) 2024, ForgeFlow S.A.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)
from odoo import fields
from odoo.tests import Form

from odoo.addons.base.tests.common import BaseCommon


class TestACHCreditTransfer(BaseCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "Partner 1"})
        cls.company = cls.env.company
        cls.company.partner_id = cls.partner.id
        cls.company.legal_id_number = "12-3456789"
        cls.payment_method_model = cls.env["account.payment.method"]
        cls.ach_out_payment_method = cls.payment_method_model.search(
            [("code", "=", "ACH-Out")], limit=1
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
        cls.bank_journal = cls.env["account.journal"].create(
            {
                "name": "Journal 1",
                "code": "J1",
                "type": "bank",
                "company_id": cls.company.id,
                "bank_account_id": bank_account.id,
            }
        )
        cls.payment_mode = cls.env["account.payment.mode"].create(
            {
                "name": "ACH",
                "company_id": cls.company.id,
                "bank_account_link": "variable",
                "payment_method_id": cls.env.ref(
                    "account_banking_ach_credit_transfer.ach_credit_transfer"
                ).id,
            }
        )
        cls.payment_mode.variable_journal_ids += cls.bank_journal
        # Provide an open payable move line for the payment order to pull.
        # (Previously this came from demo data, which is not loaded under tests.)
        payable_account = cls.env["account.account"].create(
            {
                "name": "ACH Payable",
                "code": "ACHPAY",
                "account_type": "liability_payable",
                "reconcile": True,
            }
        )
        expense_account = cls.env["account.account"].create(
            {
                "name": "ACH Expense",
                "code": "ACHEXP",
                "account_type": "expense",
            }
        )
        cls.partner.property_account_payable_id = payable_account
        purchase_journal = cls.env["account.journal"].create(
            {
                "name": "ACH Purchases",
                "code": "ACHPU",
                "type": "purchase",
                "company_id": cls.company.id,
            }
        )
        cls.bill = cls.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": cls.partner.id,
                "invoice_date": fields.Date.today(),
                "date": fields.Date.today(),
                "journal_id": purchase_journal.id,
                "payment_mode_id": cls.payment_mode.id,
                "payment_reference": "TEST-ACH-001",
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "ACH test line",
                            "quantity": 1,
                            "price_unit": 100.0,
                            "account_id": expense_account.id,
                        },
                    )
                ],
            }
        )
        cls.bill.action_post()

    def test_account_payment_order(self):
        self.payment_order = self.env["account.payment.order"].create(
            {
                "payment_type": "outbound",
                "payment_mode_id": self.payment_mode.id,
                "journal_id": self.bank_journal.id,
                "payment_method_id": self.ach_out_payment_method.id,
            }
        )
        line_create_form = Form(
            self.env["account.payment.line.create"].with_context(
                active_model="account.payment.order", active_id=self.payment_order.id
            )
        )
        line_create_form.date_type = "due"
        line_create_form.filter_date = fields.Date.today()
        line_create_form.payment_mode = "any"
        line_create_form.target_move = "all"
        line_created_due = line_create_form.save()
        line_created_due.populate()
        line_created_due.create_payment_lines()
        self.assertEqual(len(line_created_due.move_line_ids), 1)
        line_created_due.move_line_ids.partner_id.bank_ids.bank_id.routing_number = (
            "35645"
        )
        self.assertEqual(self.payment_order.state, "draft")
        self.payment_order.draft2open()
        self.assertEqual(self.payment_order.state, "open")
        self.payment_order.generate_payment_file()
        self.payment_order.generated2uploaded()
        self.assertEqual(self.payment_order.state, "uploaded")
