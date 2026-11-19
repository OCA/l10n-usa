# Copyright 2026 Binhex - Edilio Escalona Almira.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from unittest.mock import patch

from odoo.exceptions import MissingError, UserError
from odoo.tests import new_test_user
from odoo.tests.common import mute_logger

from ..services.provider_base import ProviderError
from ..services.provider_local import ProviderLocal
from .common import UsTaxBaseTest

_TAX_ENGINE_LOGGER = "odoo.addons.l10n_us_sales_tax_engine.services.tax_engine"
_AUTO_MIXIN_LOGGER = "odoo.addons.l10n_us_sales_tax_engine.models.us_tax_auto_mixin"


class TestProviderOutage(UsTaxBaseTest):
    """What a document keeps, and what it tells, when no provider answers."""

    @classmethod
    def setUpClass(cls):
        """Create the users and keep the engine's own cursor in the test.

        In test mode that cursor shares the test transaction, so the audit
        row of a blocked calculation is never committed.
        """
        super().setUpClass()
        cls.registry.enter_test_mode(cls.cr)
        cls.addClassCleanup(cls.registry.leave_test_mode)
        cls.salesman = new_test_user(
            cls.env,
            login="us_tax_outage_salesman",
            groups="sales_team.group_sale_salesman",
        )
        cls.invoicer = new_test_user(
            cls.env,
            login="us_tax_outage_invoicer",
            groups="account.group_account_invoice",
        )

    def _set_fail_policy(self, policy):
        self.env["ir.config_parameter"].sudo().set_param(
            "l10n_us_tax.fail_policy", policy
        )

    def _providers_down(self):
        return patch.object(
            ProviderLocal,
            "get_rate",
            side_effect=ProviderError("rate service unavailable"),
        )

    def _outage_notes(self, document):
        return document.sudo().message_ids.filtered(
            lambda message: "could not be calculated" in (message.body or "")
        )

    @mute_logger(_TAX_ENGINE_LOGGER, _AUTO_MIXIN_LOGGER)
    def test_recalculation_during_outage_keeps_the_order_tax(self):
        order = self._create_fl_order()
        order.action_calculate_us_tax()
        tax_before = order.order_line.tax_id
        self.assertTrue(self._us_taxes(tax_before))
        with self._providers_down():
            order.action_calculate_us_tax()
        self.assertEqual(order.us_tax_source, "error")
        self.assertEqual(order.order_line.tax_id, tax_before)

    @mute_logger(_TAX_ENGINE_LOGGER, _AUTO_MIXIN_LOGGER)
    def test_recalculation_during_outage_keeps_the_invoice_tax(self):
        move = self._create_fl_invoice()
        move.action_calculate_us_tax()
        tax_before = move.invoice_line_ids.tax_ids
        self.assertTrue(self._us_taxes(tax_before))
        with self._providers_down():
            move.action_calculate_us_tax()
        self.assertEqual(move.us_tax_source, "error")
        self.assertEqual(move.invoice_line_ids.tax_ids, tax_before)

    @mute_logger(_TAX_ENGINE_LOGGER, _AUTO_MIXIN_LOGGER)
    def test_blocked_calculation_leaves_an_error_row(self):
        """The button refuses with a UserError, and the audit row stays.

        assertRaises would roll back to a savepoint and take the row with
        it, since the engine's own cursor shares the test transaction.
        """
        self._set_fail_policy("block")
        order = self._create_fl_order()
        failure = None
        with self._providers_down():
            try:
                order.action_calculate_us_tax()
            except UserError as exc:
                failure = exc
        self.assertTrue(failure, "the block policy must stop the calculation")
        self.assertIn("could not be calculated", str(failure))
        self.assertEqual(
            self.env["us.tax.calculation.log"]
            .sudo()
            .search_count(
                [
                    ("res_model", "=", "sale.order"),
                    ("res_id", "=", order.id),
                    ("status", "=", "error"),
                ]
            ),
            1,
        )

    @mute_logger(_TAX_ENGINE_LOGGER, _AUTO_MIXIN_LOGGER)
    def test_blocked_invoice_calculation_is_a_user_error(self):
        self._set_fail_policy("block")
        move = self._create_fl_invoice(user=self.invoicer)
        with self._providers_down(), self.assertRaises(UserError):
            move.with_user(self.invoicer).action_calculate_us_tax()

    @mute_logger(_TAX_ENGINE_LOGGER, _AUTO_MIXIN_LOGGER)
    def test_confirm_during_outage_with_block_is_refused(self):
        self._set_fail_policy("block")
        order = self._create_fl_order(user=self.salesman)
        with self._providers_down(), self.assertRaises(UserError):
            order.with_user(self.salesman).action_confirm()
        self.assertEqual(order.state, "draft")

    @mute_logger(_TAX_ENGINE_LOGGER, _AUTO_MIXIN_LOGGER)
    def test_confirm_with_block_is_refused_when_the_audit_row_fails(self):
        self._set_fail_policy("block")
        order = self._create_fl_order(user=self.salesman)
        with (
            self._providers_down(),
            patch.object(
                type(self.env["us.tax.calculation.log"]),
                "log_calculation",
                side_effect=MissingError("user not visible to this cursor"),
            ),
            self.assertRaises(UserError),
        ):
            order.with_user(self.salesman).action_confirm()
        self.assertEqual(order.state, "draft")

    @mute_logger(_TAX_ENGINE_LOGGER, _AUTO_MIXIN_LOGGER)
    def test_batch_confirm_with_block_confirms_no_order(self):
        """The order the block policy stops takes the whole batch with it."""
        self._set_fail_policy("block")
        first = self._create_fl_order(user=self.salesman)
        second = self._create_fl_order(user=self.salesman)
        first_taxes = first.order_line.tax_id
        second_fails = [{"total_rate": 0.07}, ProviderError("unavailable")]
        with (
            patch.object(ProviderLocal, "get_rate", side_effect=second_fails),
            self.assertRaises(UserError) as refusal,
        ):
            (first | second).with_user(self.salesman).action_confirm()
        self.assertIn(second.name, str(refusal.exception))
        self.assertEqual((first | second).mapped("state"), ["draft", "draft"])
        self.assertEqual(first.order_line.tax_id, first_taxes)

    @mute_logger(_TAX_ENGINE_LOGGER, _AUTO_MIXIN_LOGGER)
    def test_post_during_outage_with_block_is_refused(self):
        self._set_fail_policy("block")
        move = self._create_fl_invoice(user=self.invoicer)
        with self._providers_down(), self.assertRaises(UserError):
            move.with_user(self.invoicer).action_post()
        self.assertEqual(move.state, "draft")

    @mute_logger(_TAX_ENGINE_LOGGER, _AUTO_MIXIN_LOGGER)
    def test_confirm_during_outage_with_warn_leaves_a_note(self):
        order = self._create_fl_order(user=self.salesman)
        with self._providers_down():
            order.with_user(self.salesman).action_confirm()
        self.assertEqual(order.state, "sale")
        self.assertTrue(self._outage_notes(order))

    @mute_logger(_TAX_ENGINE_LOGGER, _AUTO_MIXIN_LOGGER)
    def test_post_during_outage_with_warn_leaves_a_note(self):
        move = self._create_fl_invoice(user=self.invoicer)
        with self._providers_down():
            move.with_user(self.invoicer).action_post()
        self.assertEqual(move.state, "posted")
        self.assertTrue(self._outage_notes(move))
