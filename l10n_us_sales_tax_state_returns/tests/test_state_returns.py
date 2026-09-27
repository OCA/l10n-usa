# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase

from odoo.addons.l10n_us_sales_tax_state_returns.services import (
    state_return_builder,
)


class TestStateReturns(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.us = cls.env.ref("base.us")
        cls.Return = cls.env["us.tax.return"]
        cls.Line = cls.env["us.tax.return.line"]
        cls.Jur = cls.env["us.tax.jurisdiction"]

    def _state(self, code):
        return self.env["res.country.state"].search(
            [("code", "=", code), ("country_id", "=", self.us.id)], limit=1
        )

    def _make_return(self, code, state_tax, locals_=None):
        st = self._state(code)
        ret = self.Return.create(
            {
                "state_id": st.id,
                "date_from": "2026-01-01",
                "date_to": "2026-01-31",
                "total_sales": 10000.0,
                "exempt_sales": 1000.0,
            }
        )
        jur_state = self.Jur.create(
            {"name": code, "type": "state", "state_id": st.id, "fips_state": "00"}
        )
        self.Line.create(
            {
                "return_id": ret.id,
                "level": "state",
                "jurisdiction_id": jur_state.id,
                "taxable_base": 9000.0,
                "tax_amount": state_tax,
            }
        )
        for name, fips, base, tax in locals_ or []:
            jur = self.Jur.create(
                {
                    "name": name,
                    "type": "county",
                    "state_id": st.id,
                    "fips_state": "00",
                    "fips_county": fips,
                }
            )
            self.Line.create(
                {
                    "return_id": ret.id,
                    "level": "county",
                    "jurisdiction_id": jur.id,
                    "taxable_base": base,
                    "tax_amount": tax,
                }
            )
        ret.state = "generated"
        return ret

    def test_collection_allowance_caps(self):
        tx = self._make_return("TX", 100.0)
        self.assertAlmostEqual(
            state_return_builder.collection_allowance(tx), 0.5, places=2
        )  # 0.5% uncapped
        fl = self._make_return("FL", 2000.0)
        self.assertEqual(
            state_return_builder.collection_allowance(fl), 30.0
        )  # 2.5% of 2000 = 50, capped at 30
        pa = self._make_return("PA", 5000.0)
        self.assertEqual(
            state_return_builder.collection_allowance(pa), 25.0
        )  # 1% of 5000 = 50, capped at 25

    def test_tx_worksheet_structure_and_net(self):
        ret = self._make_return("TX", 62.50, locals_=[("Harris", "201", 1000.0, 10.0)])
        csv_text = state_return_builder.build(ret).decode("utf-8")
        self.assertIn("Texas Sales and Use Tax Return (01-114)", csv_text)
        self.assertIn("State Tax (6.25%),62.50", csv_text)
        self.assertIn("Harris", csv_text)
        self.assertIn("201", csv_text)  # county FIPS
        self.assertIn("Total Tax Collected,72.50", csv_text)
        self.assertIn("Timely Filing Discount (0.5%),0.36", csv_text)
        self.assertIn("Net Tax Due,72.14", csv_text)

    def test_fl_worksheet_has_surtax_section(self):
        ret = self._make_return("FL", 600.0)
        csv_text = state_return_builder.build(ret).decode("utf-8")
        self.assertIn("Florida Sales and Use Tax Return (DR-15)", csv_text)
        self.assertIn("Discretionary Surtax by County", csv_text)
        self.assertIn("Collection Allowance (2.5%, max $30)", csv_text)

    def test_action_supported_and_unsupported(self):
        tx = self._make_return("TX", 62.50)
        self.assertTrue(tx.state_return_supported)
        action = tx.action_export_state_return()
        self.assertEqual(action["type"], "ir.actions.act_url")
        att = self.env["ir.attachment"].search(
            [("res_model", "=", "us.tax.return"), ("res_id", "=", tx.id)]
        )
        self.assertTrue(att)

        ny = self._make_return("NY", 80.0)
        self.assertFalse(ny.state_return_supported)
        with self.assertRaises(UserError):
            ny.action_export_state_return()

    def test_action_requires_generated(self):
        tx = self._make_return("TX", 62.50)
        tx.state = "draft"
        with self.assertRaises(UserError):
            tx.action_export_state_return()

    def test_state_only_worksheet_builds(self):
        ret = self._make_return("TX", 62.50)  # no local lines
        csv_text = state_return_builder.build(ret).decode("utf-8")
        self.assertIn("Texas Sales and Use Tax Return (01-114)", csv_text)
        self.assertIn("Net Tax Due", csv_text)
