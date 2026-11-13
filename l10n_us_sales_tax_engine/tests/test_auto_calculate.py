# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import Form, tagged
from odoo.tests.common import mute_logger

from ..services.address_resolver import normalize_zip
from .common import UsTaxBaseTest

_TAX_ENGINE_LOGGER = "odoo.addons.l10n_us_sales_tax_engine.services.tax_engine"

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
class TestUsTaxAutoCalculate(UsTaxBaseTest):
    """Automatic recalculation governed by l10n_us_tax.auto_calculate."""

    @classmethod
    def setUpClass(cls):
        """Turn the automation on and map a second ZIP.

        The automation is what this class tests, and it is off by
        default, so it is enabled here rather than in the shared
        fixtures. The second ZIP maps to a jurisdiction the engine can
        price, so that changing an address still lands on a rate.
        """
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param(
            "l10n_us_tax.auto_calculate", "True"
        )
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

    def _set_auto_calculate(self, enabled):
        self.env["ir.config_parameter"].sudo().set_param(
            "l10n_us_tax.auto_calculate", "True" if enabled else "False"
        )

    def _today(self):
        return fields.Date.context_today(self.env.user)

    def _log_count(self):
        return self.env["us.tax.calculation.log"].sudo().search_count([])

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

    def _us_taxes(self, taxes):
        return taxes.filtered(lambda tax: tax.name.startswith("US Sales Tax"))

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

    def test_confirm_without_auto_calculate_assigns_no_tax(self):
        """With the automation off, confirming must not assign US tax."""
        self._set_auto_calculate(False)
        order = self._create_order()
        order.action_confirm()
        self.assertFalse(
            self._us_taxes(order.order_line.tax_id),
            "confirming with the automation off must not assign US tax",
        )

    def test_post_without_auto_calculate_assigns_no_tax(self):
        """With the automation off, posting must not assign US tax."""
        self._set_auto_calculate(False)
        move = self._create_invoice()
        move.action_post()
        self.assertEqual(move.state, "posted")
        self.assertFalse(
            self._us_taxes(move.invoice_line_ids.tax_ids),
            "posting with the automation off must not assign US tax",
        )

    def test_write_without_auto_calculate_runs_no_calculation(self):
        """With the automation off, a write must not reach the engine."""
        self._set_auto_calculate(False)
        order = self._create_order()
        before = self._log_count()
        order.order_line.product_uom_qty = 5.0
        self.assertEqual(before, self._log_count())

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
        before = self._log_count()
        extra.unlink()
        self.assertEqual(before, self._log_count())

    def test_write_tax_id_runs_no_calculation(self):
        """tax_id is written by the engine and is not a hash input."""
        order = self._create_order()
        before = self._log_count()
        order.order_line.tax_id = [(5, 0, 0)]
        self.assertEqual(before, self._log_count())

    def test_write_unrelated_field_runs_no_calculation(self):
        """note and client_order_ref are outside the hash's @api.depends."""
        order = self._create_order()
        before = self._log_count()
        order.write({"note": "Nothing to do with tax", "client_order_ref": "REF-1"})
        self.assertEqual(before, self._log_count())

    def test_write_identical_value_runs_no_calculation(self):
        """Writing the value a field already had leaves the hash untouched."""
        order = self._create_order(qty=2.0)
        before = self._log_count()
        order.order_line.product_uom_qty = 2.0
        self.assertEqual(before, self._log_count())

    def test_write_on_posted_invoice_runs_no_calculation(self):
        """A posted move is out of the allowed states and must not raise."""
        move = self._create_invoice()
        move.action_post()
        before = self._log_count()
        move.write({"ref": "REF-POSTED"})
        self.assertEqual(move.state, "posted")
        self.assertEqual(before, self._log_count())

    def test_write_on_cancelled_invoice_runs_no_calculation(self):
        """A cancelled move is out of the allowed states and must not raise."""
        move = self._create_invoice()
        move.action_post()
        move.button_cancel()
        before = self._log_count()
        move.write({"ref": "REF-CANCELLED"})
        self.assertEqual(move.state, "cancel")
        self.assertEqual(before, self._log_count())

    def test_partner_zip_change_marks_order_outdated(self):
        """A partner address change marks the document, without calculating."""
        order = self._create_order()
        self.assertFalse(order.us_tax_is_stale)
        before = self._log_count_for(order)
        self.partner_fl.zip = "33102"
        self.assertTrue(
            order.us_tax_is_stale,
            "changing the partner ZIP must mark the draft order as outdated",
        )
        self.assertEqual(
            before,
            self._log_count_for(order),
            "marking a document as outdated must not reach the engine",
        )

    def _partner_zip_change_cost(self, order_count):
        """Return the queries and log rows one customer address change costs."""
        partner = self._create_us_partner()
        for _index in range(order_count):
            self._create_order(partner=partner)
        self.env.flush_all()
        self.env.invalidate_all()
        logs_before = self._log_count()
        queries_before = self.cr.sql_log_count
        partner.zip = "33102"
        self.env.flush_all()
        return (
            self.cr.sql_log_count - queries_before,
            self._log_count() - logs_before,
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

    def test_partner_without_country_is_not_american(self):
        """A ZIP and a state do not make an address American.

        The engine and the fingerprint read the country through the same
        helper, so an address it will not price gets no fingerprint
        either and the document can never read as outdated.
        """
        partner = self._create_us_partner()
        partner.country_id = False
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
        self._set_auto_calculate(False)
        order = self._create_order()
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
        """The banner's button is one of the three ways to consume it."""
        order = self._create_order()
        self.partner_fl.zip = "33102"
        self.assertTrue(order.us_tax_is_stale)
        order.action_calculate_us_tax()
        self.assertFalse(order.us_tax_is_stale)

    def test_cron_recalculates_outdated_documents(self):
        """The cron is the unattended way to consume the outdated flag."""
        order = self._create_order()
        self._set_auto_calculate(False)
        self.partner_fl.zip = "33102"
        self.assertTrue(order.us_tax_is_stale)
        self._set_auto_calculate(True)
        self.env["sale.order"]._us_tax_cron_recalculate_stale()
        self.assertFalse(order.us_tax_is_stale)

    def test_cron_does_nothing_without_auto_calculate(self):
        """The parameter governs the cron too."""
        order = self._create_order()
        self.partner_fl.zip = "33102"
        self._set_auto_calculate(False)
        self.env["sale.order"]._us_tax_cron_recalculate_stale()
        self.assertTrue(order.us_tax_is_stale)

    def test_non_us_document_has_no_hash(self):
        """No usable US address, no hash: the engine skips it anyway."""
        partner_fr = self.env["res.partner"].create(
            {"name": "Test FR Partner", "country_id": self.env.ref("base.fr").id}
        )
        order = self.env["sale.order"].create({"partner_id": partner_fr.id})
        self.assertFalse(order.us_tax_input_hash)
        self.assertFalse(order.us_tax_is_stale)

    def test_disabling_the_engine_turns_the_automation_off(self):
        """Unticking the engine must not leave the automation enabled.

        set_values() is called instead of execute(): execute() also runs
        the module install/uninstall pass and can reload the registry,
        which leaks out of the test transaction and breaks unrelated
        modules' tests further down the same run.

        Odoo stores a False boolean config_parameter by deleting its row
        (res_config.py set_values() -> set_param(icp, False) -> unlink()),
        so what is asserted is that the parameter no longer reads as
        enabled, not that it holds the literal string "False".

        Ticking the engine back on afterwards is the point of the
        onchange: the automation stays off, so re-enabling the engine
        never revives an automation nobody asked for.
        """
        settings_form = Form(self.env["res.config.settings"])
        settings_form.us_tax_engine_active = False
        self.assertFalse(
            settings_form.us_tax_auto_calculate,
            "unticking the engine must untick the automation",
        )
        settings_form.save().set_values()
        self.assertNotEqual(
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("l10n_us_tax.auto_calculate"),
            "True",
        )
        self.env["ir.config_parameter"].sudo().set_param(
            "l10n_us_tax.engine_active", "True"
        )
        self.assertFalse(
            self.env["sale.order"]._us_tax_auto_enabled(),
            "re-enabling the engine must not revive the automation",
        )

    def test_engine_available_follows_the_engine_parameter(self):
        """The field that hides the "Calculate US Tax" button."""
        order = self._create_order()
        self.assertTrue(order.us_tax_engine_available)
        self.env["ir.config_parameter"].sudo().set_param(
            "l10n_us_tax.engine_active", "False"
        )
        order.invalidate_recordset(["us_tax_engine_available"])
        self.assertFalse(order.us_tax_engine_available)

    def test_order_create_calculates_exactly_once(self):
        """An order born with lines is priced once, by the line create."""
        before = self._log_count()
        order = self._create_order()
        self.assertEqual(
            self._log_count(),
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
        before = self._log_count()
        move = self._create_invoice()
        self.assertEqual(
            self._log_count(),
            before + 1,
            "creating an invoice with lines must reach the engine exactly once",
        )
        self.assertTrue(self._us_taxes(move.invoice_line_ids.tax_ids))
        self.assertFalse(move.us_tax_is_stale)

    def test_confirm_of_up_to_date_order_calculates_zero_times(self):
        """Confirmation is a write like any other and obeys the same guards."""
        order = self._create_order()
        self.assertFalse(order.us_tax_is_stale)
        before = self._log_count()
        order.action_confirm()
        self.assertEqual(order.state, "sale")
        self.assertEqual(
            before,
            self._log_count(),
            "confirming an up-to-date order must not reach the engine",
        )

    def test_post_of_up_to_date_invoice_calculates_zero_times(self):
        """Posting is a write like any other and obeys the same guards."""
        move = self._create_invoice(invoice_date=self._today())
        self.assertFalse(move.us_tax_is_stale)
        before = self._log_count()
        move.action_post()
        self.assertEqual(move.state, "posted")
        self.assertEqual(
            before,
            self._log_count(),
            "posting an up-to-date invoice must not reach the engine",
        )

    def test_confirm_of_stale_order_calculates_exactly_once(self):
        """An outdated order is brought up to date on confirmation."""
        order = self._create_order()
        self.partner_fl.zip = "33102"
        self.assertTrue(order.us_tax_is_stale)
        before = self._log_count_for(order)
        order.action_confirm()
        self.assertEqual(
            self._log_count_for(order),
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
        before = self._log_count_for(move)
        move.action_post()
        self.assertEqual(move.state, "posted")
        self.assertEqual(
            self._log_count_for(move),
            before + 1,
            "posting an outdated invoice must reach the engine exactly once",
        )
        self.assertEqual(
            move.us_tax_calculated_hash,
            move.us_tax_input_hash,
            "posting must not leave the invoice outdated",
        )
        self.assertTrue(self._us_taxes(move.invoice_line_ids.tax_ids))

    def test_engine_tax_is_price_excluded(self):
        """The engine's taxes never inherit account_price_include.

        Run against a company set to tax_included, which is the only
        configuration where the pin is observable: price_include falls
        back to the company setting exactly when price_include_override
        is empty.
        """
        company = self.env["res.company"].create(
            {
                "name": "US Tax Included Co",
                "country_id": self.us.id,
                "account_price_include": "tax_included",
            }
        )
        engine = self.env["us.tax.engine.service"].with_company(company)
        state_tax = engine._get_or_create_state_tax("FL", company, 0.0825)
        exempt_tax = engine._get_or_create_exempt_tax(company)
        for tax in (state_tax, exempt_tax):
            self.assertEqual(tax.price_include_override, "tax_excluded")
            self.assertFalse(
                tax.price_include,
                f'"{tax.name}" must not inherit the company price include',
            )

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
        before = self._log_count()
        dynamic.write({"name": "Renamed by the test"})
        self.assertEqual(before, self._log_count())

        product_line = move.invoice_line_ids.filtered(
            lambda line: line.display_type == "product"
        )
        self.assertEqual(product_line._us_tax_auto_parents(), move)
        before = self._log_count()
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
            self._log_count(),
            before + 1,
            "a new product line must reach the engine exactly once",
        )

    def test_section_and_note_lines_do_not_trigger(self):
        """A section or a note carries no subtotal, so it cannot move the hash."""
        order = self._create_order()
        order_hash = order.us_tax_input_hash
        move = self._create_invoice()
        move_hash = move.us_tax_input_hash
        before = self._log_count()

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

        self.assertEqual(before, self._log_count())
        self.assertEqual(order_hash, order.us_tax_input_hash)
        self.assertEqual(move_hash, move.us_tax_input_hash)

    def test_sections_get_no_tax_on_order(self):
        """Only the priced lines of an order come out with a tax on them."""
        order = self._create_order()
        order.write(
            {
                "order_line": [
                    (0, 0, {"display_type": "line_section", "name": "Materials"}),
                    (0, 0, {"display_type": "line_note", "name": "Delivered loose"}),
                ]
            }
        )
        order.action_calculate_us_tax()

        sections = order.order_line.filtered("display_type")
        self.assertEqual(len(sections), 2)
        self.assertFalse(sections.tax_id, "a section or a note must never carry a tax")
        self.assertTrue(self._us_taxes(order._get_priced_lines().tax_id))
        self.assertFalse(
            self.env["account.tax"]
            .sudo()
            .search_count(
                [
                    ("name", "=", "US Sales Tax FL 0%"),
                    ("company_id", "=", self.env.company.id),
                ]
            ),
            "no 0% state tax may be created on behalf of a section",
        )

    def test_sections_get_no_tax_on_invoice(self):
        """Only the product lines of an invoice come out with a tax on them."""
        move = self._create_invoice()
        move.write(
            {
                "invoice_line_ids": [
                    (0, 0, {"display_type": "line_section", "name": "Materials"}),
                    (0, 0, {"display_type": "line_note", "name": "Delivered loose"}),
                ]
            }
        )
        move.action_calculate_us_tax()

        sections = move.invoice_line_ids.filtered(
            lambda line: line.display_type in ("line_section", "line_note")
        )
        self.assertEqual(len(sections), 2)
        self.assertFalse(sections.tax_ids, "a section or a note must never carry a tax")
        product_lines = move.invoice_line_ids.filtered(
            lambda line: line.display_type == "product"
        )
        self.assertTrue(self._us_taxes(product_lines.tax_ids))

    def test_exempt_order_leaves_sections_untouched(self):
        """The order-wide exemption branch skips sections too."""
        self.partner_fl.us_tax_exempt = True
        order = self._create_order()
        order.write(
            {"order_line": [(0, 0, {"display_type": "line_section", "name": "S"})]}
        )
        order.action_calculate_us_tax()

        self.assertEqual(order.us_tax_source, "exempt_partner")
        section = order.order_line.filtered("display_type")
        self.assertFalse(section.tax_id)
        self.assertTrue(self._us_taxes(order._get_priced_lines().tax_id))

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
        which moves the fingerprint of an order dated any other day. That
        write goes through the mixin, so no override is needed and the
        pass prices at the confirmation date.
        """
        order = self._create_order()
        order.date_order = fields.Datetime.now() - timedelta(days=1)
        self.assertFalse(order.us_tax_is_stale)
        before = self._log_count()
        order.action_confirm()
        self.assertEqual(order.state, "sale")
        self.assertEqual(
            self._log_count(),
            before + 1,
            "confirming an order dated another day must reach the engine once",
        )

    def test_post_of_undated_invoice_calculates_zero_times(self):
        """The fingerprint holds invoice_date or today, which is what is priced."""
        move = self._create_invoice()
        self.assertFalse(move.invoice_date)
        before = self._log_count()
        move.action_post()
        self.assertEqual(move.state, "posted")
        self.assertEqual(
            before,
            self._log_count(),
            "filling in invoice_date on post must not reach the engine",
        )
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
        self._set_auto_calculate(False)
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
        before = self._log_count_for(order)
        with self.assertNoLogs("odoo.addons.l10n_us_sales_tax_engine", level="ERROR"):
            self.partner_fl.zip = "33102"
            self.env.flush_all()
            self.env["sale.order"]._us_tax_cron_recalculate_stale()
        self.assertFalse(order.us_tax_is_stale)
        self.assertEqual(order.order_line.tax_id, taxes_before)
        self.assertEqual(before, self._log_count_for(order))

    def test_invoiced_order_is_not_recalculated(self):
        """A fully invoiced order has nothing left for a new rate to reach."""
        order = self._create_order()
        order.action_confirm()
        order._create_invoices().action_post()
        self.assertEqual(order.invoice_status, "invoiced")
        taxes_before = order.order_line.tax_id
        before = self._log_count_for(order)
        with self.assertNoLogs("odoo.addons.l10n_us_sales_tax_engine", level="ERROR"):
            self.partner_fl.zip = "33102"
            self.env.flush_all()
            self.env["sale.order"]._us_tax_cron_recalculate_stale()
        self.assertFalse(order.us_tax_is_stale)
        self.assertEqual(order.order_line.tax_id, taxes_before)
        self.assertEqual(before, self._log_count_for(order))

    def test_manual_button_refuses_outside_domain(self):
        """The button stamps no hash where the engine cannot apply anything."""
        move = self._create_invoice(invoice_date=self._today())
        move.action_post()
        hash_before = move.us_tax_calculated_hash
        before = self._log_count()
        move.action_calculate_us_tax()
        self.assertEqual(move.us_tax_calculated_hash, hash_before)
        self.assertEqual(before, self._log_count())

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
        self.assertEqual(order.us_tax_calculated_hash, hash_before)
        self.assertTrue(order.us_tax_is_stale)
        self.env["sale.order"]._us_tax_cron_recalculate_stale()
        self.assertFalse(order.us_tax_is_stale)
        self.assertNotEqual(order.order_line.tax_id, taxes_before)

    def test_line_without_a_rate_does_not_stamp_hash(self):
        """One line short of a rate is a failed calculation, not a 0% one."""
        order = self._create_order_two_lines()
        hash_before = order.us_tax_calculated_hash
        self.partner_fl.zip = self._map_zip_to_a_dearer_jurisdiction()
        with self._exhaust_providers_from_call(2):
            order.order_line[0].price_unit = 150.0
        self.assertEqual(
            order.us_tax_source,
            "error",
            "a line whose providers all failed decides the document source",
        )
        self.assertEqual(order.us_tax_calculated_hash, hash_before)
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
        self._set_auto_calculate(False)
        partner.zip = "33102"
        self.assertEqual(len(orders.filtered("us_tax_is_stale")), 3)
        self._set_auto_calculate(True)
        self.env["sale.order"]._us_tax_cron_recalculate_stale(limit=2)
        self.assertEqual(
            len(orders.filtered("us_tax_is_stale")),
            1,
            "the cron must process exactly the limit, not everything found",
        )
        self.env["sale.order"]._us_tax_cron_recalculate_stale(limit=2)
        self.assertFalse(orders.filtered("us_tax_is_stale"))

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

    def test_address_without_country_is_not_us(self):
        """A ZIP and a state without a country are not an American address."""
        partner = self.env["res.partner"].create(
            {
                "name": "Test Customer No Country",
                "zip": "33101",
                "city": "Miami",
                "state_id": self.fl.id,
            }
        )
        self.assertFalse(partner.country_id)
        before = self._log_count()
        order = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": 1.0,
                            "price_unit": 100.0,
                        },
                    )
                ],
            }
        )
        self.assertFalse(order.us_tax_input_hash)
        self.assertFalse(order.us_tax_is_stale)
        self.assertEqual(
            before,
            self._log_count(),
            "a document the engine skips must leave no audit trail",
        )

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
        self.assertFalse(order.us_tax_is_stale)

        before = self._log_count()
        billing.zip = "33102"
        self.assertTrue(
            order.us_tax_is_stale,
            "the billing partner's address must be a hash input",
        )
        self.assertEqual(before, self._log_count())

    def test_zip_plus_four_is_not_a_change(self):
        """A ZIP+4 is the same ZIP to the engine, so the tax stays current.

        The fingerprint runs the address through the very helpers the
        engine uses, and normalize_zip() keeps the first five digits, so
        the extended form must reach neither the banner nor the engine.
        """
        order = self._create_order()
        hash_before = order.us_tax_input_hash
        self.assertTrue(order.us_tax_calculated_hash)
        before = self._log_count_for(order)
        self.partner_fl.zip = "33101-4521"
        self.env.flush_all()
        self.assertEqual(order.us_tax_input_hash, hash_before)
        self.assertFalse(order.us_tax_is_stale)
        self.assertEqual(
            before,
            self._log_count_for(order),
            "a ZIP the engine normalizes away must run no calculation",
        )

    def test_city_case_and_padding_are_not_a_change(self):
        """The city is upper-cased and stripped before it is fingerprinted."""
        order = self._create_order()
        hash_before = order.us_tax_input_hash
        before = self._log_count_for(order)
        self.partner_fl.city = "  miami  "
        self.env.flush_all()
        self.assertEqual(order.us_tax_input_hash, hash_before)
        self.assertFalse(order.us_tax_is_stale)
        self.assertEqual(before, self._log_count_for(order))

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
