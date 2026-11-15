# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import base64
from datetime import date

from .common import UsTaxBaseTest


class TestRuleImport(UsTaxBaseTest):
    def _import(self, csv_text, state):
        wizard = self.env["us.tax.rule.import.wizard"].create(
            {
                "state_id": state.id,
                "matrix_file": base64.b64encode(csv_text.encode()),
                "matrix_filename": "matrix.csv",
            }
        )
        action = wizard.action_import()
        return self.env["us.tax.import.batch"].browse(action["res_id"])

    def test_matrix_import_creates_rules(self):
        csv_text = (
            "category_code,taxable,rate_override,effective_date,end_date\n"
            "TANGIBLE,1,,2020-01-01,\n"
            "FOOD,0,,2020-01-01,\n"
        )
        self._import(csv_text, self.ny)
        Rule = self.env["us.tax.rule"]
        food = self.env["us.tax.product.category"].search([("code", "=", "FOOD")])
        taxable, _ = Rule.is_taxable(self.ny.id, food.id, date=date(2025, 6, 1))
        self.assertFalse(taxable)
        taxable, _ = Rule.is_taxable(
            self.ny.id, self.cat_tangible.id, date=date(2025, 6, 1)
        )
        self.assertTrue(taxable)

    def test_unknown_category_skipped(self):
        batch = self._import(
            "category_code,taxable,rate_override,effective_date,end_date\n"
            "NOPE,1,,2020-01-01,\n",
            self.ny,
        )
        self.assertEqual(batch.status, "done")
        self.assertEqual(batch.records_skipped, 1)
        self.assertEqual(batch.records_created, 0)

    def test_reimport_same_period_updates(self):
        csv_text = (
            "category_code,taxable,rate_override,effective_date,end_date\n"
            "TANGIBLE,1,,2020-01-01,\n"
        )
        self._import(csv_text, self.ny)
        batch = self._import(csv_text, self.ny)
        self.assertEqual(batch.records_updated, 1)
        self.assertEqual(batch.records_created, 0)
        rules = self.env["us.tax.rule"].search(
            [
                ("state_id", "=", self.ny.id),
                ("product_tax_category_id", "=", self.cat_tangible.id),
            ]
        )
        self.assertEqual(len(rules), 1)

    def test_bad_row_recorded_not_aborted(self):
        # A malformed date row is skipped + logged; good rows still import.
        batch = self._import(
            "category_code,taxable,rate_override,effective_date,end_date\n"
            "TANGIBLE,1,,2020-01-01,\n"
            "FOOD,1,,notadate,\n",
            self.ny,
        )
        self.assertEqual(batch.records_created, 1)
        self.assertEqual(batch.records_skipped, 1)
        self.assertIn("row 3", batch.error_log)
        self.assertTrue(
            self.env["us.tax.rule"].search_count(
                [
                    ("state_id", "=", self.ny.id),
                    ("product_tax_category_id", "=", self.cat_tangible.id),
                ]
            )
        )

    def test_ccyymmdd_date_format(self):
        self._import(
            "category_code,taxable,rate_override,effective_date,end_date\n"
            "TANGIBLE,1,,20200101,\n",
            self.ny,
        )
        rule = self.env["us.tax.rule"].search(
            [
                ("state_id", "=", self.ny.id),
                ("product_tax_category_id", "=", self.cat_tangible.id),
            ]
        )
        self.assertEqual(rule.effective_date, date(2020, 1, 1))

    def test_future_rule_supersedes_on_effective_date(self):
        self._import(
            "category_code,taxable,rate_override,effective_date,end_date\n"
            "TANGIBLE,1,,2020-01-01,\n",
            self.ny,
        )
        # A future-effective rule flips TANGIBLE to exempt from 2026.
        self._import(
            "category_code,taxable,rate_override,effective_date,end_date\n"
            "TANGIBLE,0,,2026-01-01,\n",
            self.ny,
        )
        Rule = self.env["us.tax.rule"]
        rules = Rule.search(
            [
                ("state_id", "=", self.ny.id),
                ("product_tax_category_id", "=", self.cat_tangible.id),
            ],
            order="effective_date",
        )
        self.assertEqual(len(rules), 2)
        # Prior open rule closed the day before the new one starts.
        self.assertEqual(rules[0].end_date, date(2025, 12, 31))
        self.assertFalse(rules[1].end_date)
        # Date-filtered activation: taxable in 2025, exempt from 2026.
        self.assertTrue(
            Rule.is_taxable(self.ny.id, self.cat_tangible.id, date(2025, 6, 1))[0]
        )
        self.assertFalse(
            Rule.is_taxable(self.ny.id, self.cat_tangible.id, date(2026, 6, 1))[0]
        )
