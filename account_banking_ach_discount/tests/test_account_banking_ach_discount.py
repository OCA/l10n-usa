# Copyright (C) 2024, ForgeFlow S.A.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)

from datetime import datetime, timedelta

from odoo.tests.common import Form, TransactionCase


class TestPayment(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.payment_method_model = cls.env["account.payment.method"]
        cls.payment_term_model = cls.env["account.payment.term"]
        cls.account_invoice_model = cls.env["account.move"]
        cls.account_model = cls.env["account.account"]
        Journal = cls.env["account.journal"]

        cls.journal_sale = Journal.search([("type", "=", "sale")], limit=1)
        cls.income_account = cls.account_model.search(
            [
                (
                    "account_type",
                    "=",
                    "income_other",
                )
            ],
            limit=1,
        )
        cls.partner = cls.env["res.partner"].create({"name": "Partner 1"})
        cls.company = cls.env.ref("base.main_company")
        cls.company.partner_id = cls.partner.id
        cls.company.legal_id_number = "12-3456789"
        cls.payment_method_line = cls.env["account.payment.method.line"].search(
            [("code", "=", "ACH-In")], limit=1
        )
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
        cls.mandate = cls.env["account.banking.mandate"].create(
            {
                "partner_bank_id": bank_account.id,
                "signature_date": "2024-01-01",
                "company_id": cls.company.id,
                "delay_days": 1,
            }
        )
        cls.mandate.validate()
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
            [("type", "=", "bank"), ("company_id", "=", cls.env.user.company_id.id)],
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

        # Create account for invoice discount
        cls.account_discount = cls.account_model.create(
            dict(
                code="custaccdiscount",
                name="Discount Expenses",
                account_type="expense",
                reconcile=True,
            )
        )

        # Create Payment term
        cls.payment_term = cls.payment_term_model.create(
            dict(
                name="5%10 NET30",
                is_discount=True,
                note="5% discount if payment done within 10 days, otherwise net",
                line_ids=[
                    (
                        0,
                        0,
                        {
                            "value": "balance",
                            "discount_percentage": 5.0,
                            "discount_days": 10,
                            "discount_expense_account_id": cls.account_discount.id,
                            "days": 30,
                        },
                    )
                ],
            )
        )

    def test_account_payment_order_ach_discount(self):

        # Create customer invoice
        self.customer_invoice = self.account_invoice_model.create(
            dict(
                name="Test Customer Invoice",
                move_type="out_invoice",
                invoice_date=datetime.today() - timedelta(days=1),
                invoice_payment_term_id=self.payment_term.id,
                journal_id=self.journal_sale.id,
                partner_id=self.partner.id,
            )
        )
        # Prepare invoice line values
        self.customer_invoice.write(
            {
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.env.ref("product.product_product_5").id,
                            "quantity": 10.0,
                            "account_id": self.income_account.id,
                            "name": "product test 5",
                            "price_unit": 100.00,
                        },
                    )
                ]
            }
        )
        # Validate customer invoice
        self.customer_invoice.action_post()

        with Form(
            self.env["account.payment.register"].with_context(
                active_ids=self.customer_invoice.ids,
                batch=True,
                active_model="account.move",
            )
        ) as register_wizard_form:
            register_wizard_form.payment_method_line_id = self.payment_method_line
            register_wizard = register_wizard_form.save()
        # check 5% discount applied on payment
        self.assertEqual(
            register_wizard.payment_difference,
            self.customer_invoice.amount_total * 0.05,
        )
        payment_order_dict = register_wizard.make_payments()
        payment_order = self.env["account.payment.order"].browse(
            payment_order_dict["res_id"]
        )
        payment_order.journal_id = self.journal_c1.id
        payment_order.draft2open()
        payment_order.payment_line_ids.payment_ids.mandate_id = self.mandate
        payment_order.generate_payment_file()
        payment_order.generated2uploaded()
