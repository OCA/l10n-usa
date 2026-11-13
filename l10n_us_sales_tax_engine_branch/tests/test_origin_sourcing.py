# Copyright 2026 Binhex - Edilio Escalona Almira.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo.exceptions import ValidationError
from odoo.fields import Command
from odoo.tests import new_test_user

from .common import UsTaxBranchCommon


class TestOriginSourcing(UsTaxBranchCommon):
    """Origin-based sourcing: setting, document check and engine address."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.settings_user = new_test_user(
            cls.env,
            login="us_tax_branch_settings",
            groups="base.group_system,base.group_partner_manager",
            company_id=cls.root.id,
            company_ids=[Command.set((cls.root | cls.branch_a1 | cls.branch_a2).ids)],
        )

    def _set_sourcing(self, company, sourcing):
        settings = (
            self.env["res.config.settings"]
            .with_user(self.settings_user)
            .with_company(company)
            .create({"us_tax_sourcing": sourcing})
        )
        settings.execute()

    def test_sourcing_default_destination(self):
        self.assertEqual(self.branch_a1.us_tax_sourcing, "destination")
        settings = (
            self.env["res.config.settings"]
            .with_user(self.settings_user)
            .with_company(self.branch_a1)
            .create({})
        )
        self.assertEqual(settings.us_tax_sourcing, "destination")

    def test_origin_requires_us_address(self):
        self._set_sourcing(self.branch_a1, "origin")
        self.assertEqual(self.branch_a1.us_tax_sourcing, "origin")
        with self.assertRaises(ValidationError):
            self.branch_a1.with_user(self.settings_user).zip = False
        no_zip = self._create_branch("US Tax Branch No ZIP", False, self.fl)
        with self.assertRaises(ValidationError):
            no_zip.us_tax_sourcing = "origin"
        no_state = self._create_branch(
            "US Tax Branch No State", "32991", self.env["res.country.state"]
        )
        with self.assertRaises(ValidationError):
            no_state.us_tax_sourcing = "origin"
        foreign = self._create_branch("US Tax Branch ES", "28001", self.fl)
        foreign.country_id = self.env.ref("base.es")
        with self.assertRaises(ValidationError):
            foreign.us_tax_sourcing = "origin"

    def _create_move(self, company, partner, move_type):
        vals = {
            "move_type": move_type,
            "company_id": company.id,
            "partner_id": partner.id,
        }
        if move_type != "entry":
            vals["invoice_line_ids"] = [
                Command.create(
                    {
                        "product_id": self.product.id,
                        "quantity": 1.0,
                        "price_unit": 100.0,
                    }
                )
            ]
        return (
            self.env["account.move"]
            .with_user(self.user)
            .with_company(company)
            .create(vals)
        )

    def test_default_check_intrastate(self):
        self._set_sourcing(self.branch_a1, "origin")
        order = self._create_order(self.branch_a1, self.partner_fl)
        self.assertTrue(order.us_tax_based_on_company)
        self.assertFalse(order.us_tax_origin_out_of_state)
        invoice = self._create_move(self.branch_a1, self.partner_fl, "out_invoice")
        self.assertTrue(invoice.us_tax_based_on_company)

    def test_default_check_interstate(self):
        self._set_sourcing(self.branch_a1, "origin")
        order = self._create_order(self.branch_a1, self.partner_tx)
        self.assertTrue(order.us_tax_based_on_company)
        order = self._create_order(self.branch_a1, self.partner_no_address)
        self.assertTrue(order.us_tax_based_on_company)
        order = self._create_order(self.branch_a1, self.partner_foreign)
        self.assertFalse(order.us_tax_based_on_company)

    def test_out_of_state_warning(self):
        self._set_sourcing(self.branch_a1, "origin")
        order = self._create_order(self.branch_a1, self.partner_tx)
        self.assertTrue(order.us_tax_origin_out_of_state)
        order.us_tax_based_on_company = False
        self.assertFalse(order.us_tax_origin_out_of_state)
        for partner in (self.partner_fl, self.partner_no_address):
            order = self._create_order(self.branch_a1, partner)
            self.assertFalse(order.us_tax_origin_out_of_state)
        invoice = self._create_move(self.branch_a1, self.partner_tx, "out_invoice")
        self.assertTrue(invoice.us_tax_origin_out_of_state)
        # An invoice from an order warns with the same rule.
        order = self._create_order(self.branch_a1, self.partner_tx)
        order.us_tax_based_on_company = False
        invoice = self._invoice_orders(order)
        self.assertFalse(invoice.us_tax_origin_out_of_state)
        invoice.us_tax_based_on_company = True
        self.assertTrue(invoice.us_tax_origin_out_of_state)

    def test_default_check_destination_company(self):
        order = self._create_order(self.branch_a1, self.partner_fl)
        self.assertFalse(order.us_tax_based_on_company)

    def test_partner_or_company_change_does_not_recompute(self):
        self._set_sourcing(self.branch_a1, "origin")
        checked = self._create_order(self.branch_a1, self.partner_fl)
        unchecked = self._create_order(self.branch_a1, self.partner_foreign)
        manual = self._create_order(self.branch_a1, self.partner_fl)
        manual.us_tax_based_on_company = False
        self.assertTrue(checked.us_tax_based_on_company)
        self.assertFalse(unchecked.us_tax_based_on_company)
        # Store the values as a saved form would before anything else changes.
        self.env.flush_all()
        self.partner_fl.country_id = self.env.ref("base.es")
        self.partner_foreign.write({"country_id": self.us.id, "state_id": self.fl.id})
        self._set_sourcing(self.branch_a1, "destination")
        self.env.flush_all()
        self.env.invalidate_all()
        self.assertTrue(checked.us_tax_based_on_company)
        self.assertFalse(unchecked.us_tax_based_on_company)
        self.assertFalse(manual.us_tax_based_on_company)
        # A new delivery address on the document itself does recompute it.
        self._set_sourcing(self.branch_a1, "origin")
        manual.partner_shipping_id = self.partner_tx
        self.assertTrue(manual.us_tax_based_on_company)

    def test_vendor_bill_never_checked(self):
        self._set_sourcing(self.branch_a1, "origin")
        bill = self._create_move(self.branch_a1, self.partner_fl, "in_invoice")
        self.assertFalse(bill.us_tax_based_on_company)
        entry = self._create_move(self.branch_a1, self.partner_fl, "entry")
        self.assertFalse(entry.us_tax_based_on_company)

    def _invoice_orders(self, orders):
        orders.action_confirm()
        invoices = orders._create_invoices()
        invoices.invoice_date = "2026-01-15"
        return invoices

    def test_invoice_inherits_check_and_rate(self):
        self._set_sourcing(self.branch_a1, "origin")
        order = self._create_order(self.branch_a1, self.partner_fl)
        self.assertTrue(order.us_tax_based_on_company)
        invoice = self._invoice_orders(order)
        self.assertTrue(invoice.us_tax_based_on_company)
        invoice.action_post()
        self.assertEqual(order.order_line.tax_id.name, "US Sales Tax FL 6.5%")
        self.assertEqual(invoice.invoice_line_ids.tax_ids, order.order_line.tax_id)

    def test_grouped_invoicing_splits_by_check(self):
        self._set_sourcing(self.branch_a1, "origin")
        checked = self._create_order(self.branch_a1, self.partner_fl)
        unchecked = self._create_order(self.branch_a1, self.partner_fl)
        unchecked.us_tax_based_on_company = False
        invoices = self._invoice_orders(checked | unchecked)
        self.assertEqual(len(invoices), 2)
        self.assertEqual(
            sorted(invoices.mapped("us_tax_based_on_company")), [False, True]
        )

    def test_refund_keeps_check(self):
        self._set_sourcing(self.branch_a1, "origin")
        order = self._create_order(self.branch_a1, self.partner_fl)
        invoice = self._invoice_orders(order)
        invoice.action_post()
        refund = invoice._reverse_moves()
        self.assertEqual(refund.move_type, "out_refund")
        self.assertTrue(refund.us_tax_based_on_company)

    def _logs(self, record):
        return self.env["us.tax.calculation.log"].search(
            [("res_model", "=", record._name), ("res_id", "=", record.id)]
        )

    def test_origin_uses_company_zip_and_state(self):
        self._set_sourcing(self.branch_a1, "origin")
        order = self._create_order(self.branch_a1, self.partner_fl)
        order.action_calculate_us_tax()
        tax = order.order_line.tax_id
        self.assertEqual(tax.name, "US Sales Tax FL 6.5%")
        self.assertEqual(tax.amount, 6.5)
        self.assertEqual(tax.company_id, self.root)
        self.assertEqual(self._logs(order).shipping_zip, "32991")

    def test_manual_check_interstate_uses_company(self):
        order = self._create_order(self.branch_a1, self.partner_tx)
        self.assertFalse(order.us_tax_based_on_company)
        order.us_tax_based_on_company = True
        order.action_calculate_us_tax()
        self.assertEqual(order.order_line.tax_id.name, "US Sales Tax FL 6.5%")

    def test_origin_non_us_customer_skips(self):
        self._set_sourcing(self.branch_a1, "origin")
        order = self._create_order(self.branch_a1, self.partner_foreign)
        order.us_tax_based_on_company = True
        order.action_calculate_us_tax()
        self.assertEqual(order.us_tax_source, "skip_non_us")
        us_taxes = order.order_line.tax_id.filtered(
            lambda tax: tax.name.startswith("US Sales Tax")
        )
        self.assertFalse(us_taxes)

    def test_origin_customer_without_address(self):
        self._set_sourcing(self.branch_a1, "origin")
        order = self._create_order(self.branch_a1, self.partner_no_address)
        order.action_calculate_us_tax()
        self.assertEqual(order.order_line.tax_id.name, "US Sales Tax FL 6.5%")

    def test_incomplete_company_address_falls_back(self):
        no_zip = self._create_branch("US Tax Branch No ZIP", False, self.fl)
        self.user.company_ids = [Command.link(no_zip.id)]
        order = self._create_order(no_zip, self.partner_fl)
        order.us_tax_based_on_company = True
        with self.assertLogs(
            "odoo.addons.l10n_us_sales_tax_engine_branch.services.tax_engine",
            level="WARNING",
        ):
            order.action_calculate_us_tax()
        self.assertEqual(order.order_line.tax_id.name, "US Sales Tax FL 7%")
        self.assertEqual(self._logs(order).shipping_zip, "33101")

    def test_single_engine_run_per_action(self):
        self._set_sourcing(self.branch_a1, "origin")
        order = self._create_order(self.branch_a1, self.partner_fl)
        order.action_calculate_us_tax()
        self.assertEqual(len(self._logs(order)), 1)
        order.action_confirm()
        self.assertEqual(len(self._logs(order)), 2)

    def test_standalone_company_unchanged(self):
        standalone = self.env["res.company"].create(
            {
                "name": "US Tax Standalone",
                "zip": "32991",
                "state_id": self.fl.id,
                "country_id": self.us.id,
            }
        )
        self.env["us.tax.nexus"].create(
            {"company_id": standalone.id, "state_id": self.fl.id}
        )
        self.user.company_ids = [Command.link(standalone.id)]
        order = self._create_order(standalone, self.partner_fl)
        self.assertFalse(order.us_tax_based_on_company)
        order.action_calculate_us_tax()
        tax = order.order_line.tax_id
        self.assertEqual(tax.name, "US Sales Tax FL 7%")
        self.assertEqual(tax.company_id, standalone)
        log = self._logs(order)
        self.assertEqual(log.shipping_zip, "33101")
        self.assertEqual(log.source, order.us_tax_source)

    def test_log_records_sourcing(self):
        self._set_sourcing(self.branch_a1, "origin")
        origin_order = self._create_order(self.branch_a1, self.partner_tx)
        origin_order.action_calculate_us_tax()
        self.assertEqual(self._logs(origin_order).us_tax_sourcing, "origin")
        invoice = self._create_move(self.branch_a1, self.partner_fl, "out_invoice")
        invoice.action_calculate_us_tax()
        self.assertEqual(self._logs(invoice).us_tax_sourcing, "origin")
        destination_order = self._create_order(self.branch_a1, self.partner_tx)
        destination_order.us_tax_based_on_company = False
        destination_order.action_calculate_us_tax()
        log = self._logs(destination_order)
        self.assertEqual(log.source, "exempt_nexus")
        self.assertEqual(log.us_tax_sourcing, "destination")
