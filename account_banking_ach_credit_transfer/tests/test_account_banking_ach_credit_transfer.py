# Copyright (C) 2024, ForgeFlow S.A.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)
from odoo import Command, fields
from odoo.tests import Form, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestACHCreditTransfer(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data["company"]
        cls.env.user.company_id = cls.company.id
        cls.env.user.groups_id |= cls.env.ref(
            "account_payment_order.group_account_payment"
        )
        cls.company.legal_id_number = "12-3456789"
        cls.partner = cls.partner_a
        cls.ach_out_payment_method = cls.env["account.payment.method"].search(
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
        # Originating (company) bank account on the order's bank journal.
        cls.company_bank = cls.env["res.partner.bank"].create(
            {
                "acc_number": "0099999999999999",
                "partner_id": cls.company.partner_id.id,
                "bank_id": cls.acme_bank.id,
                "company_id": cls.company.id,
            }
        )
        cls.bank_journal = cls.company_data["default_journal_bank"]
        cls.bank_journal.bank_account_id = cls.company_bank.id
        # Destination (vendor) bank account.
        cls.env["res.partner.bank"].create(
            {
                "acc_number": "0023032234211123",
                "partner_id": cls.partner.id,
                "bank_id": cls.acme_bank.id,
                "company_id": cls.company.id,
            }
        )
        cls.payment_mode = cls.env["account.payment.mode"].create(
            {
                "name": "ACH Out",
                "company_id": cls.company.id,
                "payment_method_id": cls.ach_out_payment_method.id,
                "bank_account_link": "variable",
                "variable_journal_ids": [Command.set(cls.bank_journal.ids)],
            }
        )
        # A single posted vendor bill, due today and isolated in the test
        # company, gives the order exactly one payable line to select -
        # independent of demo data and the run date (the previous test relied
        # on ambient demo bills, whose due-as-of-today count drifts with the
        # calendar).
        cls.bill = cls.init_invoice(
            "in_invoice",
            partner=cls.partner,
            invoice_date=fields.Date.today(),
            amounts=[100.0],
            company=cls.company,
        )
        cls.bill.write(
            {
                "invoice_payment_term_id": False,
                "invoice_date_due": fields.Date.today(),
                "payment_mode_id": cls.payment_mode.id,
                "payment_reference": "ACH-TEST-001",
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
        self.assertEqual(self.payment_order.state, "draft")
        self.payment_order.draft2open()
        self.assertEqual(self.payment_order.state, "open")
        self.payment_order.generate_payment_file()
        self.payment_order.generated2uploaded()
        self.assertEqual(self.payment_order.state, "uploaded")
