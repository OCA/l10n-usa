# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from datetime import timedelta
from unittest.mock import patch

from freezegun import freeze_time

from odoo import fields
from odoo.tests import tagged

from ..services.address_resolver import normalize_zip
from .common import UsTaxBaseTest

SALE_ORDER_HASH_DEPENDS = [
    "partner_id.zip",
    "partner_id.state_id",
    "partner_id.city",
    "partner_id.street",
    "partner_id.country_id",
    "partner_shipping_id.zip",
    "partner_shipping_id.state_id",
    "partner_shipping_id.city",
    "partner_shipping_id.street",
    "partner_shipping_id.country_id",
    "partner_invoice_id.zip",
    "partner_invoice_id.state_id",
    "partner_invoice_id.city",
    "partner_invoice_id.street",
    "partner_invoice_id.country_id",
    "partner_id.us_tax_exempt",
    "us_tax_based_on_shipping",
    "date_order",
    "company_id",
    "order_line.price_subtotal",
    "order_line.product_id.us_tax_category_id",
    "order_line.qty_invoiced",
    "state",
    "locked",
    "invoice_status",
]

ACCOUNT_MOVE_HASH_DEPENDS = [
    "partner_id.zip",
    "partner_id.state_id",
    "partner_id.city",
    "partner_id.street",
    "partner_id.country_id",
    "partner_shipping_id.zip",
    "partner_shipping_id.state_id",
    "partner_shipping_id.city",
    "partner_shipping_id.street",
    "partner_shipping_id.country_id",
    "partner_id.us_tax_exempt",
    "invoice_date",
    "company_id",
    "invoice_line_ids.price_subtotal",
    "invoice_line_ids.product_id.us_tax_category_id",
    "state",
    "move_type",
]


@tagged("post_install", "-at_install")
class TestUsTaxOutdated(UsTaxBaseTest):
    """Outdated tax detection, the manual button and the validation pass."""

    @classmethod
    def setUpClass(cls):
        """Map a second ZIP to a jurisdiction the engine can price.

        Changing an address to it still lands on a rate.
        """
        super().setUpClass()
        cls.env["us.tax.zip.mapping"].create(
            {
                "zip": "33102",
                "state_id": cls.fl.id,
                "jurisdiction_id": cls.jur_miami.id,
                "county": "MIAMI-DADE",
                "confidence": 1.0,
                "source": "test",
            }
        )

    def _today(self):
        return fields.Date.context_today(self.env.user)

    def setUp(self):
        """Count every entry into the engine, the early returns included.

        An audit row is only written on the paths that price something, so
        counting rows misses a calculation the engine skipped or one the
        block policy stopped.
        """
        super().setUp()
        service = type(self.env["us.tax.engine.service"])
        original = service._process
        calls = self._engine_calls = []

        def counting(service_self, *args, **kwargs):
            calls.append(
                (
                    kwargs.get("res_model", args[0] if args else None),
                    kwargs.get("res_id", args[1] if len(args) > 1 else None),
                )
            )
            return original(service_self, *args, **kwargs)

        patcher = patch.object(service, "_process", counting)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _engine_runs(self):
        return len(self._engine_calls)

    def _engine_runs_for(self, document):
        return self._engine_calls.count((document._name, document.id))

    def _log_count_for(self, document):
        """Count only this document's rows.

        A partner address change reaches every draft document of that
        partner, so a global count cannot tell whether the document
        under test was the one recalculated.
        """
        return (
            self.env["us.tax.calculation.log"]
            .sudo()
            .search_count(
                [("res_model", "=", document._name), ("res_id", "=", document.id)]
            )
        )

    def _create_order(self, qty=1.0, partner=None, calculate=True):
        """Create a one-line order, priced with the button unless told not to."""
        partner = partner or self.partner_fl
        order = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "partner_shipping_id": partner.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": qty,
                            "price_unit": 100.0,
                        },
                    )
                ],
            }
        )
        if calculate:
            order.action_calculate_us_tax()
        return order

    def _create_order_two_lines(self, partner=None):
        partner = partner or self.partner_fl
        line = {
            "product_id": self.product.id,
            "product_uom_qty": 1.0,
            "price_unit": 100.0,
        }
        order = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "partner_shipping_id": partner.id,
                "order_line": [(0, 0, dict(line)), (0, 0, dict(line))],
            }
        )
        order.action_calculate_us_tax()
        return order

    def _create_us_partner(self, zip_code="33101"):
        return self.env["res.partner"].create(
            {
                "name": "Test Customer FL 2",
                "zip": zip_code,
                "city": "Miami",
                "state_id": self.fl.id,
                "country_id": self.us.id,
            }
        )

    def _map_zip_to_a_dearer_jurisdiction(self, zip_code="33103"):
        """Map a second ZIP to a jurisdiction whose rate is 8%, not 7%."""
        jurisdiction = self.env["us.tax.jurisdiction"].create(
            {
                "name": "Broward",
                "type": "county",
                "state_id": self.fl.id,
                "county": "BROWARD",
            }
        )
        for category in (False, self.cat_tangible.id):
            self.env["us.tax.rate"].create(
                {
                    "jurisdiction_id": jurisdiction.id,
                    "product_tax_category_id": category,
                    "state_rate": 0.06,
                    "county_rate": 0.02,
                    "city_rate": 0.00,
                    "district_rate": 0.00,
                    "effective_date": "2020-01-01",
                    "source": "test",
                }
            )
        self.env["us.tax.zip.mapping"].create(
            {
                "zip": zip_code,
                "state_id": self.fl.id,
                "jurisdiction_id": jurisdiction.id,
                "county": "BROWARD",
                "confidence": 1.0,
                "source": "test",
            }
        )
        return zip_code

    def _exhaust_providers_from_call(self, nth):
        """Patch _get_rate to report exhausted providers from its nth call on.

        Mirrors what _handle_all_failed returns under the warn and manual
        policies: a 0% rate carrying the "error" source, rather than an
        exception.
        """
        service = type(self.env["us.tax.engine.service"])
        original = service._get_rate
        calls = []

        def failing(self_service, **kwargs):
            calls.append(kwargs.get("zip_code"))
            if len(calls) >= nth:
                return {
                    "total_rate": 0.0,
                    "state_rate": 0.0,
                    "county_rate": 0.0,
                    "city_rate": 0.0,
                    "district_rate": 0.0,
                    "source": "error",
                }
            return original(self_service, **kwargs)

        return patch.object(service, "_get_rate", failing)

    def _create_invoice(self, move_type="out_invoice", invoice_date=None):
        vals = {
            "move_type": move_type,
            "partner_id": self.partner_fl.id,
            "invoice_line_ids": [
                (
                    0,
                    0,
                    {
                        "product_id": self.product.id,
                        "quantity": 1,
                        "price_unit": 100.0,
                    },
                )
            ],
        }
        if invoice_date:
            vals["invoice_date"] = invoice_date
        move = self.env["account.move"].create(vals)
        move.action_calculate_us_tax()
        return move

    def test_partner_zip_change_marks_order_outdated(self):
        """A partner address change marks the document, without calculating."""
        order = self._create_order()
        self.assertFalse(order.us_tax_is_stale)
        before = self._engine_runs_for(order)
        self.partner_fl.zip = "33102"
        self.assertTrue(
            order.us_tax_is_stale,
            "changing the partner ZIP must mark the draft order as outdated",
        )
        self.assertEqual(
            before,
            self._engine_runs_for(order),
            "marking a document as outdated must not reach the engine",
        )

    def _partner_zip_change_cost(self, order_count):
        """Return the queries and engine runs one customer address change costs."""
        partner = self._create_us_partner()
        for _index in range(order_count):
            self._create_order(partner=partner)
        self.env.flush_all()
        self.env.invalidate_all()
        runs_before = self._engine_runs()
        queries_before = self.cr.sql_log_count
        partner.zip = "33102"
        self.env.flush_all()
        return (
            self.cr.sql_log_count - queries_before,
            self._engine_runs() - runs_before,
        )

    def test_partner_address_change_does_not_scale_with_documents(self):
        """One address change costs the same at twenty documents as at one.

        Marking is what a customer address change does, and the ORM
        batches all of it: the documents are read in one prefetch and
        their two fingerprint columns land in a single UPDATE. What
        grows with the number of documents is the SHA-256 of each, in
        Python. The engine is not involved, so no provider quota is
        spent inside the transaction that writes the address.
        """
        one_document = self._partner_zip_change_cost(1)
        twenty_documents = self._partner_zip_change_cost(20)
        self.assertEqual(
            twenty_documents,
            one_document,
            "marking a customer's documents must not cost a query per document",
        )
        self.assertEqual(one_document[1], 0, "marking must not reach the engine")

    def test_foreign_state_without_country_is_not_american(self):
        """A partner with no country takes the one of its state.

        The engine and the fingerprint read the country through the same
        helper, so an address it will not price gets no fingerprint
        either and the document can never read as outdated.
        """
        partner = self._create_us_partner()
        partner.write(
            {"country_id": False, "state_id": self.env.ref("base.state_ca_qc").id}
        )
        order = self._create_order(partner=partner)
        self.assertFalse(order.us_tax_input_hash)
        self.assertFalse(order.us_tax_is_stale)
        before = self._log_count_for(order)
        order.action_calculate_us_tax()
        self.assertEqual(order.us_tax_source, "skip_non_us")
        self.assertFalse(self._us_taxes(order.order_line.tax_id))
        self.assertEqual(
            self._log_count_for(order),
            before,
            "an address the engine skips leaves no audit row",
        )

    def test_never_calculated_document_is_not_outdated(self):
        """An empty calculated hash means "never calculated", not "outdated"."""
        order = self._create_order(calculate=False)
        self.assertFalse(order.us_tax_calculated_hash)
        self.assertFalse(order.us_tax_is_stale)

    def test_value_returning_to_its_original_clears_the_outdated_flag(self):
        """The hash detects the real change, not the fact that a write ran."""
        order = self._create_order()
        self.partner_fl.zip = "33102"
        self.assertTrue(order.us_tax_is_stale)
        self.partner_fl.zip = "33101"
        self.assertFalse(order.us_tax_is_stale)

    def test_manual_button_clears_the_outdated_flag(self):
        """The banner's button is one of the ways to consume it."""
        order = self._create_order()
        self.partner_fl.zip = "33102"
        self.assertTrue(order.us_tax_is_stale)
        order.action_calculate_us_tax()
        self.assertFalse(order.us_tax_is_stale)

    def test_non_us_document_has_no_hash(self):
        """No usable US address, no hash: the engine skips it anyway."""
        partner_fr = self.env["res.partner"].create(
            {"name": "Test FR Partner", "country_id": self.env.ref("base.fr").id}
        )
        order = self.env["sale.order"].create({"partner_id": partner_fr.id})
        self.assertFalse(order.us_tax_input_hash)
        self.assertFalse(order.us_tax_is_stale)

    def test_engine_available_follows_the_engine_parameter(self):
        """The field that hides the "Calculate US Tax" button."""
        order = self._create_order()
        self.assertTrue(order.us_tax_engine_available)
        self.env["ir.config_parameter"].sudo().set_param(
            "l10n_us_tax.engine_active", "False"
        )
        order.invalidate_recordset(["us_tax_engine_available"])
        self.assertFalse(order.us_tax_engine_available)

    def test_confirm_of_up_to_date_order_calculates_once(self):
        """Rates and nexus are not in the fingerprint, so confirming prices."""
        order = self._create_order()
        self.assertFalse(order.us_tax_is_stale)
        before = self._engine_runs()
        order.action_confirm()
        self.assertEqual(order.state, "sale")
        self.assertEqual(self._engine_runs(), before + 1)

    def test_post_of_up_to_date_invoice_calculates_once(self):
        """Rates and nexus are not in the fingerprint, so posting prices."""
        move = self._create_invoice(invoice_date=self._today())
        self.assertFalse(move.us_tax_is_stale)
        before = self._engine_runs()
        move.action_post()
        self.assertEqual(move.state, "posted")
        self.assertEqual(self._engine_runs(), before + 1)

    def test_confirm_applies_a_rate_raised_after_the_calculation(self):
        order = self._create_order()
        self.assertEqual(self._us_taxes(order.order_line.tax_id).amount, 7.0)
        self.env["us.tax.rate"].search(
            [("jurisdiction_id", "=", self.jur_miami.id)]
        ).write({"county_rate": 0.02})
        order.action_confirm()
        self.assertEqual(self._us_taxes(order.order_line.tax_id).amount, 8.0)

    def test_post_after_the_nexus_is_dropped_leaves_the_invoice_exempt(self):
        move = self._create_invoice(invoice_date=self._today())
        self.assertEqual(move.us_tax_source, "local")
        self.env["us.tax.nexus"].search(
            [("company_id", "=", move.company_id.id), ("state_id", "=", self.fl.id)]
        ).active = False
        move.action_post()
        self.assertEqual(move.us_tax_source, "exempt_nexus")

    def test_other_write_during_confirmation_does_not_recalculate(self):
        """Only the confirmation write itself forces a calculation.

        sale_stock writes procurement_group_id on the order inside
        action_confirm(); that write goes through the fingerprint guard.
        """
        order = self._create_order()
        order.action_confirm()
        before = self._engine_runs()
        order.with_context(us_tax_validating=True).write({"client_order_ref": "X"})
        self.assertEqual(self._engine_runs(), before)

    def test_confirm_of_stale_order_calculates_exactly_once(self):
        """An outdated order is brought up to date on confirmation."""
        order = self._create_order()
        self.partner_fl.zip = "33102"
        self.assertTrue(order.us_tax_is_stale)
        before = self._engine_runs_for(order)
        order.action_confirm()
        self.assertEqual(
            self._engine_runs_for(order),
            before + 1,
            "confirming an outdated order must reach the engine exactly once",
        )
        self.assertFalse(order.us_tax_is_stale)

    def test_post_of_stale_invoice_calculates_exactly_once(self):
        """An outdated invoice is brought up to date on posting.

        _post() recalculates before super(): a posted move has its
        tax_ids frozen, so the pass that lands the tax is the only one
        there can be. us_tax_is_stale reads False on a posted move by
        construction, so what proves the calculation landed is the
        calculated hash matching the input hash.
        """
        move = self._create_invoice(invoice_date=self._today())
        self.partner_fl.zip = "33102"
        self.assertTrue(move.us_tax_is_stale)
        before = self._engine_runs_for(move)
        move.action_post()
        self.assertEqual(move.state, "posted")
        self.assertEqual(
            self._engine_runs_for(move),
            before + 1,
            "posting an outdated invoice must reach the engine exactly once",
        )
        self.assertEqual(
            move.us_tax_calculated_hash,
            move.us_tax_input_hash,
            "posting must not leave the invoice outdated",
        )
        self.assertTrue(self._us_taxes(move.invoice_line_ids.tax_ids))

    def test_section_and_note_lines_do_not_move_the_hash(self):
        """A section or a note carries no subtotal, so it cannot move the hash."""
        order = self._create_order()
        order_hash = order.us_tax_input_hash
        move = self._create_invoice()
        move_hash = move.us_tax_input_hash

        order.write(
            {
                "order_line": [
                    (0, 0, {"display_type": "line_section", "name": "Materials"}),
                    (0, 0, {"display_type": "line_note", "name": "Delivered loose"}),
                ]
            }
        )
        move.write(
            {
                "invoice_line_ids": [
                    (0, 0, {"display_type": "line_section", "name": "Materials"}),
                    (0, 0, {"display_type": "line_note", "name": "Delivered loose"}),
                ]
            }
        )

        self.assertEqual(order_hash, order.us_tax_input_hash)
        self.assertEqual(move_hash, move.us_tax_input_hash)
        self.assertFalse(order.us_tax_is_stale)
        self.assertFalse(move.us_tax_is_stale)

    def test_zero_subtotal_product_line_is_still_cleared(self):
        """A product line that drops to zero loses its previous tax.

        The apply step filters on display_type rather than on the
        subtotal precisely so this line still goes through it. The order
        keeps a second, priced line: a document with nothing left to
        price at all is a different case, unrelated to this filter.
        """
        order = self._create_order()
        zero_line = order.order_line
        self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": self.product.id,
                "product_uom_qty": 1.0,
                "price_unit": 200.0,
            }
        )
        previous_tax = zero_line.tax_id
        self.assertTrue(self._us_taxes(previous_tax))

        zero_line.price_unit = 0.0
        order.action_calculate_us_tax()

        self.assertFalse(
            zero_line.tax_id & previous_tax,
            "the tax of the previous calculation must be gone",
        )
        self.assertTrue(
            self._us_taxes(zero_line.tax_id),
            "a zero line still carries an explicit tax, never an empty field",
        )

    def test_confirm_of_stale_order_next_day_calculates_exactly_once(self):
        """Core's own confirmation write is the only trigger there is.

        Core stamps date_order = now() in _prepare_confirmation_values(),
        which moves the fingerprint of an order priced on any other day.
        That write goes through the mixin, so no override is needed and the
        pass prices at the confirmation date.
        """
        order = self._create_order()
        order.date_order = fields.Datetime.now() - timedelta(days=1)
        order.action_calculate_us_tax()
        self.assertFalse(order.us_tax_is_stale)
        before = self._engine_runs()
        order.action_confirm()
        self.assertEqual(order.state, "sale")
        self.assertEqual(
            self._engine_runs(),
            before + 1,
            "confirming an order dated another day must reach the engine once",
        )

    def test_post_of_undated_invoice_calculates_once(self):
        """Filling in invoice_date on post does not price the invoice again."""
        move = self._create_invoice()
        self.assertFalse(move.invoice_date)
        before = self._engine_runs()
        move.action_post()
        self.assertEqual(move.state, "posted")
        self.assertEqual(self._engine_runs(), before + 1)
        self.assertFalse(move.us_tax_is_stale)

    def test_partner_zip_change_leaves_posted_invoice_untouched(self):
        """The fingerprint is only maintained inside the state domain."""
        move = self._create_invoice(invoice_date=self._today())
        move.action_post()
        hash_before = move.us_tax_input_hash
        write_date_before = move.write_date
        self.partner_fl.zip = "33102"
        self.env.flush_all()
        move.invalidate_recordset()
        self.assertEqual(move.us_tax_input_hash, hash_before)
        self.assertEqual(move.write_date, write_date_before)
        self.assertFalse(move.us_tax_is_stale)

    def test_partner_zip_change_does_not_hash_vendor_bill(self):
        """res.partner.invoice_ids covers every move type; the domain does not."""
        bill = self._create_invoice(move_type="in_invoice")
        self.assertFalse(bill.us_tax_input_hash)
        self.partner_fl.zip = "33102"
        self.env.flush_all()
        bill.invalidate_recordset()
        self.assertFalse(bill.us_tax_input_hash)

    def test_draft_reset_invoice_becomes_stale(self):
        """state is in the depends so a document coming back is re-marked."""
        move = self._create_invoice(invoice_date=self._today())
        move.action_post()
        self.partner_fl.zip = "33102"
        self.assertFalse(move.us_tax_is_stale)
        move.button_draft()
        self.assertEqual(move.state, "draft")
        self.assertTrue(
            move.us_tax_is_stale,
            "a move whose address moved while posted must come back outdated",
        )

    def test_locked_order_is_not_recalculated(self):
        """tax_id is a protected field on a locked order, so it stays out."""
        order = self._create_order()
        order.action_confirm()
        order.action_lock()
        taxes_before = order.order_line.tax_id
        before = self._engine_runs_for(order)
        with self.assertNoLogs("odoo.addons.l10n_us_sales_tax_engine", level="ERROR"):
            self.partner_fl.zip = "33102"
            self.env.flush_all()
            order.action_calculate_us_tax()
        self.assertFalse(order.us_tax_is_stale)
        self.assertEqual(order.order_line.tax_id, taxes_before)
        self.assertEqual(before, self._engine_runs_for(order))

    def test_invoiced_order_is_not_recalculated(self):
        """A fully invoiced order has nothing left for a new rate to reach."""
        order = self._create_order()
        order.action_confirm()
        order._create_invoices().action_post()
        self.assertEqual(order.invoice_status, "invoiced")
        taxes_before = order.order_line.tax_id
        before = self._engine_runs_for(order)
        with self.assertNoLogs("odoo.addons.l10n_us_sales_tax_engine", level="ERROR"):
            self.partner_fl.zip = "33102"
            self.env.flush_all()
            order.action_calculate_us_tax()
        self.assertFalse(order.us_tax_is_stale)
        self.assertEqual(order.order_line.tax_id, taxes_before)
        self.assertEqual(before, self._engine_runs_for(order))

    def test_partially_invoiced_order_keeps_the_invoiced_line_tax(self):
        """Only the lines nothing has been invoiced from follow a new rate."""
        order = self._create_order_two_lines()
        order.action_confirm()
        invoiced_line, open_line = order.order_line
        invoice = order._create_invoices()
        invoice.invoice_line_ids.filtered(
            lambda line: line.sale_line_ids == open_line
        ).unlink()
        invoice.action_post()
        tax_before = invoiced_line.tax_id
        self.partner_fl.zip = self._map_zip_to_a_dearer_jurisdiction()
        order.action_calculate_us_tax()
        self.assertEqual(invoiced_line.tax_id, tax_before)
        self.assertEqual(self._us_taxes(open_line.tax_id).name, "US Sales Tax FL 8%")

    @freeze_time("2026-01-15 20:00:00")
    def test_undated_invoice_hash_ignores_the_user_timezone(self):
        """At 20:00 UTC Kiritimati and Pago Pago are on different days."""
        move = self._create_invoice()
        dates = {
            move.with_context(tz=tz)._us_tax_get_date()
            for tz in ("Pacific/Kiritimati", "Pacific/Pago_Pago")
        }
        self.assertEqual(dates, {"2026-01-15"})

    def test_manual_button_refuses_outside_domain(self):
        """The button stamps no hash where the engine cannot apply anything."""
        move = self._create_invoice(invoice_date=self._today())
        move.action_post()
        hash_before = move.us_tax_calculated_hash
        before = self._engine_runs()
        move.action_calculate_us_tax()
        self.assertEqual(move.us_tax_calculated_hash, hash_before)
        self.assertEqual(before, self._engine_runs())

    def test_failed_manual_calculation_marks_the_order_outdated(self):
        """The inputs did not move, but the tax on the lines is not theirs."""
        order = self._create_order()
        self.assertFalse(order.us_tax_is_stale)
        with self._exhaust_providers_from_call(1):
            order.action_calculate_us_tax()
        self.assertEqual(order.us_tax_source, "error")
        self.assertTrue(order.us_tax_is_stale)
        order.action_calculate_us_tax()
        self.assertFalse(order.us_tax_is_stale)

    def test_order_shipped_abroad_stops_being_outdated(self):
        order = self._create_order()
        order.partner_shipping_id = self.env["res.partner"].create(
            {"name": "Test CA", "country_id": self.env.ref("base.ca").id}
        )
        order.action_calculate_us_tax()
        self.assertFalse(self._us_taxes(order.order_line.tax_id))
        self.assertFalse(order.us_tax_is_stale)
        runs = self._engine_runs_for(order)
        order.write({"client_order_ref": "A"})
        order.write({"client_order_ref": "B"})
        order.write({"origin": "C"})
        self.assertEqual(self._engine_runs_for(order), runs)

    def test_engine_uses_document_hooks(self):
        """The engine taxes the address the document hook returns."""
        order = self._create_order()
        address = {
            "zip": "33102",
            "state": "FL",
            "city": "MIAMI",
            "county": "",
            "address": "Elsewhere, Miami, FL 33102",
            "country_code": "US",
            "partner_id": self.partner_fl.id,
        }
        with patch.object(
            type(self.env["sale.order"]),
            "_us_tax_get_address",
            lambda self: address,
        ):
            self.env["us.tax.engine.service"].calculate_for_sale_order(order)
        row = (
            self.env["us.tax.calculation.log"]
            .sudo()
            .search([("res_model", "=", "sale.order")], order="id desc", limit=1)
        )
        self.assertEqual(row.shipping_zip, "33102")

    def test_hash_depends_unchanged(self):
        """The callable @api.depends resolves per concrete model."""
        expected = {
            "sale.order": SALE_ORDER_HASH_DEPENDS,
            "account.move": ACCOUNT_MOVE_HASH_DEPENDS,
        }
        for model_name, depends in expected.items():
            field = self.env[model_name]._fields["us_tax_input_hash"]
            resolved = self.env.registry.field_depends[field]
            self.assertEqual(
                sorted(resolved),
                sorted(depends),
                f"us_tax_input_hash dependencies changed on {model_name}",
            )
            self.assertEqual(len(resolved), len(depends))

    def test_address_without_country_is_fingerprinted_as_its_state(self):
        """A ZIP and a US state without a country are an American address."""
        partner = self._create_us_partner()
        partner.country_id = False
        order = self._create_order(partner=partner)
        self.assertEqual(order.us_tax_source, "local")
        self.assertTrue(order.us_tax_input_hash)
        self.assertFalse(order.us_tax_is_stale)

    def test_billing_address_change_marks_order_outdated(self):
        """The billing partner counts when the order is not shipping-based."""
        billing = self.env["res.partner"].create(
            {
                "name": "Test Billing FL",
                "zip": "33101",
                "city": "Miami",
                "state_id": self.fl.id,
                "country_id": self.us.id,
            }
        )
        order = self._create_order()
        order.write(
            {"us_tax_based_on_shipping": False, "partner_invoice_id": billing.id}
        )
        order.action_calculate_us_tax()
        self.assertFalse(order.us_tax_is_stale)

        before = self._engine_runs()
        billing.zip = "33102"
        self.assertTrue(
            order.us_tax_is_stale,
            "the billing partner's address must be a hash input",
        )
        self.assertEqual(before, self._engine_runs())

    def test_zip_plus_four_is_not_a_change(self):
        """A ZIP+4 is the same ZIP to the engine, so the tax stays current.

        The fingerprint runs the address through the very helpers the
        engine uses, and normalize_zip() keeps the first five digits, so
        the extended form must reach neither the banner nor the engine.
        """
        order = self._create_order()
        hash_before = order.us_tax_input_hash
        self.assertTrue(order.us_tax_calculated_hash)
        before = self._engine_runs_for(order)
        self.partner_fl.zip = "33101-4521"
        self.env.flush_all()
        self.assertEqual(order.us_tax_input_hash, hash_before)
        self.assertFalse(order.us_tax_is_stale)
        self.assertEqual(
            before,
            self._engine_runs_for(order),
            "a ZIP the engine normalizes away must run no calculation",
        )

    def test_city_case_and_padding_are_not_a_change(self):
        """The city is upper-cased and stripped before it is fingerprinted."""
        order = self._create_order()
        hash_before = order.us_tax_input_hash
        before = self._engine_runs_for(order)
        self.partner_fl.city = "  miami  "
        self.env.flush_all()
        self.assertEqual(order.us_tax_input_hash, hash_before)
        self.assertFalse(order.us_tax_is_stale)
        self.assertEqual(before, self._engine_runs_for(order))

    def test_normalize_zip(self):
        """Five digits or nothing, whatever the input looks like."""
        cases = {
            "33101": "33101",
            "33101-4521": "33101",
            " 33101 ": "33101",
            "331014521": "33101",
            "3310": "",
            "": "",
            "ABCDE": "",
        }
        for raw, expected in cases.items():
            self.assertEqual(normalize_zip(raw), expected, f"ZIP {raw!r}")
