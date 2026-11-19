# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from unittest.mock import patch

from freezegun import freeze_time

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import mute_logger

from .common import UsTaxBaseTest

_TAX_ENGINE_LOGGER = "odoo.addons.l10n_us_sales_tax_engine.services.tax_engine"


@tagged("post_install", "-at_install")
class TestUsTaxLiveMode(UsTaxBaseTest):
    """The live mode: draft documents follow their changes, and the cron."""

    @classmethod
    def setUpClass(cls):
        """Turn the live mode on and map a second ZIP.

        The live mode is what this class tests, and the default is
        on_validate, so it is set here rather than in the shared fixtures.
        The second ZIP maps to a jurisdiction the engine can price, so
        that changing an address still lands on a rate.
        """
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param("l10n_us_tax.auto_mode", "live")
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

    def _set_auto_mode(self, mode):
        self.env["ir.config_parameter"].sudo().set_param("l10n_us_tax.auto_mode", mode)

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

    def _log_count(self):
        return self.env["us.tax.calculation.log"].sudo().search_count([])

    def _create_order(self, qty=1.0, partner=None):
        partner = partner or self.partner_fl
        return self.env["sale.order"].create(
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

    def _create_order_two_lines(self, partner=None):
        partner = partner or self.partner_fl
        line = {
            "product_id": self.product.id,
            "product_uom_qty": 1.0,
            "price_unit": 100.0,
        }
        return self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "partner_shipping_id": partner.id,
                "order_line": [(0, 0, dict(line)), (0, 0, dict(line))],
            }
        )

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

    def _fail_state_tax_from_call(self, nth):
        """Patch _get_or_create_state_tax to raise from its nth call on."""
        service = type(self.env["us.tax.engine.service"])
        original = service._get_or_create_state_tax
        calls = []

        def failing(self_service, state_code, company, rate_pct=0.0):
            calls.append(state_code)
            if len(calls) >= nth:
                raise ValueError("engine apply failure under test")
            return original(self_service, state_code, company, rate_pct)

        return patch.object(service, "_get_or_create_state_tax", failing)

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
        return self.env["account.move"].create(vals)

    def test_write_in_off_mode_runs_no_calculation(self):
        self._set_auto_mode("off")
        order = self._create_order()
        before = self._engine_runs()
        order.order_line.product_uom_qty = 5.0
        self.assertEqual(before, self._engine_runs())

    def test_write_quantity_recalculates_in_the_same_write(self):
        """Changing a quantity leaves the line's tax already recalculated."""
        order = self._create_order()
        order.order_line.product_uom_qty = 5.0
        self.assertTrue(
            self._us_taxes(order.order_line.tax_id),
            "changing a quantity must leave the line with US tax",
        )
        self.assertFalse(order.us_tax_is_stale)

    def test_new_line_gets_us_tax(self):
        """A line added to a draft order comes out with US tax on it."""
        order = self._create_order()
        new_line = self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": self.product.id,
                "product_uom_qty": 3.0,
                "price_unit": 50.0,
            }
        )
        self.assertTrue(
            self._us_taxes(new_line.tax_id),
            "a new line must come out with US tax on it",
        )

    def test_invoice_line_create_recalculates(self):
        """A line added to a draft invoice comes out with US tax on it."""
        move = self._create_invoice()
        move.write(
            {
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "quantity": 2,
                            "price_unit": 25.0,
                        },
                    )
                ]
            }
        )
        self.assertTrue(
            self._us_taxes(move.invoice_line_ids.tax_ids),
            "a new invoice line must come out with US tax on it",
        )

    def test_unlink_line_runs_no_calculation(self):
        """Removing a line cannot change the rate of the remaining ones."""
        order = self._create_order()
        extra = self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": self.product.id,
                "product_uom_qty": 1.0,
                "price_unit": 10.0,
            }
        )
        before = self._engine_runs()
        extra.unlink()
        self.assertEqual(before, self._engine_runs())

    def test_write_tax_id_runs_no_calculation(self):
        """tax_id is written by the engine and is not a hash input."""
        order = self._create_order()
        before = self._engine_runs()
        order.order_line.tax_id = [(5, 0, 0)]
        self.assertEqual(before, self._engine_runs())

    def test_write_unrelated_field_runs_no_calculation(self):
        """note and client_order_ref are outside the hash's @api.depends."""
        order = self._create_order()
        before = self._engine_runs()
        order.write({"note": "Nothing to do with tax", "client_order_ref": "REF-1"})
        self.assertEqual(before, self._engine_runs())

    def test_write_identical_value_runs_no_calculation(self):
        """Writing the value a field already had leaves the hash untouched."""
        order = self._create_order(qty=2.0)
        before = self._engine_runs()
        order.order_line.product_uom_qty = 2.0
        self.assertEqual(before, self._engine_runs())

    def test_write_on_posted_invoice_runs_no_calculation(self):
        """A posted move is out of the allowed states and must not raise."""
        move = self._create_invoice()
        move.action_post()
        before = self._engine_runs()
        move.write({"ref": "REF-POSTED"})
        self.assertEqual(move.state, "posted")
        self.assertEqual(before, self._engine_runs())

    def test_write_on_cancelled_invoice_runs_no_calculation(self):
        """A cancelled move is out of the allowed states and must not raise."""
        move = self._create_invoice()
        move.action_post()
        move.button_cancel()
        before = self._engine_runs()
        move.write({"ref": "REF-CANCELLED"})
        self.assertEqual(move.state, "cancel")
        self.assertEqual(before, self._engine_runs())

    def test_order_create_calculates_exactly_once(self):
        """An order born with lines is priced once, by the line create."""
        before = self._engine_runs()
        order = self._create_order()
        self.assertEqual(
            self._engine_runs(),
            before + 1,
            "creating an order with lines must reach the engine exactly once",
        )
        self.assertTrue(self._us_taxes(order.order_line.tax_id))
        self.assertFalse(order.us_tax_is_stale)

    def test_invoice_create_calculates_exactly_once(self):
        """The line create and the move create share a single calculation.

        Both reach _us_tax_auto_recalculate(); the second one finds the
        hash already stamped by the first and returns without pricing.
        """
        before = self._engine_runs()
        move = self._create_invoice()
        self.assertEqual(
            self._engine_runs(),
            before + 1,
            "creating an invoice with lines must reach the engine exactly once",
        )
        self.assertTrue(self._us_taxes(move.invoice_line_ids.tax_ids))
        self.assertFalse(move.us_tax_is_stale)

    def test_dynamic_lines_do_not_trigger(self):
        """Core's tax and payment-term lines stay out of the automation."""
        move = self._create_invoice()
        dynamic = move.line_ids.filtered(
            lambda line: line.display_type in ("tax", "payment_term")
        )
        self.assertTrue(dynamic, "a draft invoice carries tax and term lines")
        self.assertFalse(
            dynamic._us_tax_auto_parents(),
            "core's dynamic lines must not reach the engine",
        )
        before = self._engine_runs()
        dynamic.write({"name": "Renamed by the test"})
        self.assertEqual(before, self._engine_runs())

        product_line = move.invoice_line_ids.filtered(
            lambda line: line.display_type == "product"
        )
        self.assertEqual(product_line._us_tax_auto_parents(), move)
        before = self._engine_runs()
        move.write(
            {
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "quantity": 1,
                            "price_unit": 40.0,
                        },
                    )
                ]
            }
        )
        self.assertEqual(
            self._engine_runs(),
            before + 1,
            "a new product line must reach the engine exactly once",
        )

    def test_section_and_note_lines_do_not_trigger(self):
        """A section or a note carries no subtotal, so it cannot move the hash."""
        order = self._create_order()
        order_hash = order.us_tax_input_hash
        move = self._create_invoice()
        move_hash = move.us_tax_input_hash
        before = self._engine_runs()

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

        self.assertEqual(before, self._engine_runs())
        self.assertEqual(order_hash, order.us_tax_input_hash)
        self.assertEqual(move_hash, move.us_tax_input_hash)

    def test_writes_after_shipping_abroad_run_no_calculation(self):
        """A document the engine no longer prices is not priced again."""
        order = self._create_order()
        order.partner_shipping_id = self.env["res.partner"].create(
            {"name": "Test CA", "country_id": self.env.ref("base.ca").id}
        )
        self.assertFalse(self._us_taxes(order.order_line.tax_id))
        self.assertFalse(order.us_tax_is_stale)
        runs = self._engine_runs_for(order)
        order.write({"client_order_ref": "A"})
        order.write({"client_order_ref": "B"})
        order.write({"origin": "C"})
        self.assertEqual(self._engine_runs_for(order), runs)

    def test_cron_recalculates_outdated_documents(self):
        """The cron is the unattended way to consume the outdated flag."""
        order = self._create_order()
        self._set_auto_mode("off")
        self.partner_fl.zip = "33102"
        self.assertTrue(order.us_tax_is_stale)
        self._set_auto_mode("live")
        self.env["sale.order"]._us_tax_cron_recalculate_stale()
        self.assertFalse(order.us_tax_is_stale)

    def test_cron_runs_in_the_live_mode_only(self):
        order = self._create_order()
        self.partner_fl.zip = "33102"
        self._set_auto_mode("on_validate")
        self.env["sale.order"]._us_tax_cron_recalculate_stale()
        self.assertTrue(order.us_tax_is_stale)

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
            self.env["sale.order"]._us_tax_cron_recalculate_stale()
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
            self.env["sale.order"]._us_tax_cron_recalculate_stale()
        self.assertFalse(order.us_tax_is_stale)
        self.assertEqual(order.order_line.tax_id, taxes_before)
        self.assertEqual(before, self._engine_runs_for(order))

    @mute_logger(_TAX_ENGINE_LOGGER)
    def test_failed_apply_does_not_stamp_hash(self):
        """A failure halfway through the lines leaves nothing behind.

        The ZIP change only marks the order; the price write is what
        reaches the engine, so the patch is in force while the tax is
        applied and the second line raises with the first already
        written.
        """
        order = self._create_order_two_lines()
        dearer_zip = self._map_zip_to_a_dearer_jurisdiction()
        taxes_before = order.order_line.tax_id
        hash_before = order.us_tax_calculated_hash
        self.assertTrue(hash_before)
        self.partner_fl.zip = dearer_zip
        with self._fail_state_tax_from_call(2):
            order.order_line[0].price_unit = 150.0
        self.assertEqual(
            order.order_line[0].price_unit,
            150.0,
            "the write that triggered the calculation must survive it",
        )
        self.assertEqual(
            order.order_line.tax_id,
            taxes_before,
            "no line may keep a tax from a calculation that failed",
        )
        self.assertFalse(order.us_tax_calculated_hash)
        self.assertTrue(order.us_tax_is_stale)
        self.env["sale.order"]._us_tax_cron_recalculate_stale()
        self.assertFalse(order.us_tax_is_stale)
        self.assertNotEqual(order.order_line.tax_id, taxes_before)

    def test_line_without_a_rate_does_not_stamp_hash(self):
        """One line short of a rate is a failed calculation, not a 0% one."""
        order = self._create_order_two_lines()
        self.partner_fl.zip = self._map_zip_to_a_dearer_jurisdiction()
        with self._exhaust_providers_from_call(2):
            order.order_line[0].price_unit = 150.0
        self.assertEqual(
            order.us_tax_source,
            "error",
            "a line whose providers all failed decides the document source",
        )
        self.assertFalse(order.us_tax_calculated_hash)
        self.assertTrue(order.us_tax_is_stale)
        log = (
            self.env["us.tax.calculation.log"]
            .sudo()
            .search(
                [("res_model", "=", "sale.order"), ("res_id", "=", order.id)],
                order="id desc",
                limit=1,
            )
        )
        self.assertEqual(log.status, "error")

    @mute_logger(_TAX_ENGINE_LOGGER)
    def test_first_failed_calculation_is_retried_by_the_cron(self):
        """A document whose very first calculation failed stays in the queue.

        The failure leaves no calculated hash, so staleness cannot rest on
        that column alone: the attempt is what tells a document that was
        tried and failed apart from one that was never calculated.
        """
        with self._fail_state_tax_from_call(1):
            order = self._create_order()
        self.assertFalse(order.us_tax_calculated_hash)
        self.assertTrue(order.us_tax_input_hash)
        self.assertTrue(order.us_tax_auto_attempt_at)
        self.assertTrue(
            order.us_tax_is_stale,
            "a first calculation that failed leaves the document outdated",
        )
        self.env["sale.order"]._us_tax_cron_recalculate_stale()
        self.assertEqual(order.us_tax_calculated_hash, order.us_tax_input_hash)
        self.assertFalse(order.us_tax_is_stale)
        self.assertTrue(self._us_taxes(order.order_line.tax_id))

    @mute_logger(_TAX_ENGINE_LOGGER)
    def test_cron_stamps_attempt_on_failure(self):
        """The attempt is stamped either way, or the queue never moves."""
        order = self._create_order()
        stale_attempt = "2020-01-01 00:00:00"
        order.with_context(us_tax_skip_auto=True).write(
            {"us_tax_auto_attempt_at": stale_attempt}
        )
        with self._fail_state_tax_from_call(1):
            self.partner_fl.zip = "33102"
            self.env.flush_all()
            self.assertTrue(order.us_tax_is_stale)
            self.env["sale.order"]._us_tax_cron_recalculate_stale()
        self.assertGreater(
            order.us_tax_auto_attempt_at,
            fields.Datetime.to_datetime(stale_attempt),
            "a run that failed must still move the document down the queue",
        )
        self.assertTrue(order.us_tax_is_stale)

    def test_cron_search_is_limited(self):
        """The limit reaches SQL, and the next run takes the ones behind."""
        partner = self._create_us_partner()
        orders = self.env["sale.order"].browse()
        for _index in range(3):
            orders |= self._create_order(partner=partner)
        self._set_auto_mode("off")
        partner.zip = "33102"
        self.assertEqual(len(orders.filtered("us_tax_is_stale")), 3)
        self._set_auto_mode("live")
        self.env["sale.order"]._us_tax_cron_recalculate_stale(limit=2)
        self.assertEqual(
            len(orders.filtered("us_tax_is_stale")),
            1,
            "the cron must process exactly the limit, not everything found",
        )
        self.env["sale.order"]._us_tax_cron_recalculate_stale(limit=2)
        self.assertFalse(orders.filtered("us_tax_is_stale"))

    def test_cron_works_in_batches_and_reports_what_is_left(self):
        """A run takes, a small batch per call, what it has not attempted."""
        partner = self._create_us_partner()
        with freeze_time("2026-01-15 10:00:00"):
            for _index in range(3):
                self._create_order(partner=partner)
            self._set_auto_mode("off")
            partner.zip = "33102"
            self._set_auto_mode("live")
        cron = self.env.ref(
            "l10n_us_sales_tax_engine.ir_cron_recalculate_outdated_us_tax_sale_order"
        )
        cron.nextcall = "2026-01-15 11:00:00"
        progress = []
        runs_before = self._engine_runs()
        with (
            freeze_time("2026-01-15 11:00:00"),
            patch.object(
                type(self.env["ir.cron"]),
                "_notify_progress",
                lambda _cron, **kwargs: progress.append(kwargs),
            ),
        ):
            for _call in range(3):
                self.env["sale.order"].with_context(
                    cron_id=cron.id
                )._us_tax_cron_recalculate_stale(limit=2)
        self.assertEqual(
            progress, [{"done": 2, "remaining": 1}, {"done": 1, "remaining": 0}]
        )
        self.assertEqual(self._engine_runs() - runs_before, 3)

    def test_run_manually_reports_what_is_left(self):
        """Run Manually brings no cron_id, and still reports the remainder."""
        partner = self._create_us_partner()
        orders = self.env["sale.order"].browse()
        for _index in range(3):
            orders |= self._create_order(partner=partner)
        self._set_auto_mode("off")
        partner.zip = "33102"
        self._set_auto_mode("live")
        cron = self.env.ref(
            "l10n_us_sales_tax_engine.ir_cron_recalculate_outdated_us_tax_sale_order"
        )
        model_class = type(self.env["sale.order"])
        recalculate = model_class._us_tax_cron_recalculate_stale
        with patch.object(
            model_class,
            "_us_tax_cron_recalculate_stale",
            lambda model, limit=10: recalculate(model, limit=2),
        ):
            cron.method_direct_trigger()
        progress = self.env["ir.cron.progress"].search(
            [("cron_id", "=", cron.id)], order="id desc", limit=1
        )
        self.assertEqual((progress.done, progress.remaining), (2, 1))
        self.assertEqual(len(orders.filtered("us_tax_is_stale")), 1)
