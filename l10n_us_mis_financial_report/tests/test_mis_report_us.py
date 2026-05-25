# Copyright 2026 Ledo <https://ledoweb.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.tests.common import TransactionCase


class TestMisReportUs(TransactionCase):
    """Verify US-GAAP P&L and Balance Sheet MIS templates."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Minimal accounts covering every US-specific KPI expression
        cls.acc_cash = cls._account("TMUS100", "Test Cash", "asset_cash")
        cls.acc_ar = cls._account(
            "TMUS130", "Test AR", "asset_receivable", reconcile=True
        )
        cls.acc_equipment = cls._account("TMUS180", "Test Equipment", "asset_fixed")
        cls.acc_accum_dep = cls._account(
            "TMUS181", "Test Accum Dep", "asset_fixed"
        )
        cls.acc_loan = cls._account(
            "TMUS270", "Test LT Loan", "liability_non_current"
        )
        cls.acc_equity = cls._account("TMUS310", "Test Equity", "equity")
        cls.acc_revenue = cls._account("TMUS400", "Test Revenue", "income")
        cls.acc_other_inc = cls._account(
            "TMUS401", "Test Interest Income", "income_other"
        )
        cls.acc_cogs = cls._account("TMUS500", "Test COGS", "expense_direct_cost")
        cls.acc_opex = cls._account("TMUS600", "Test OpEx", "expense")
        cls.acc_dep = cls._account(
            "TMUS610", "Test Depreciation", "expense_depreciation"
        )
        cls.journal = cls.env["account.journal"].create(
            {"name": "US MIS Test Journal", "type": "general", "code": "UMIS"}
        )
        cls._post_entries()

    @classmethod
    def _account(cls, code, name, account_type, reconcile=False):
        return cls.env["account.account"].create(
            {
                "code": code,
                "name": name,
                "account_type": account_type,
                "reconcile": reconcile,
            }
        )

    @classmethod
    def _post_entries(cls):
        """Post 3 balanced journal entries that populate every US KPI."""
        entries = cls.env["account.move"].create(
            [
                # Entry 1: opening equity + cash
                {
                    "journal_id": cls.journal.id,
                    "date": "2024-01-01",
                    "line_ids": [
                        (0, 0, {"account_id": cls.acc_cash.id, "debit": 20000.0}),
                        (0, 0, {"account_id": cls.acc_equity.id, "credit": 20000.0}),
                    ],
                },
                # Entry 2: sale $10k, COGS $6k, interest $0.5k
                # gross_profit = 10000 - 6000 = 4000
                # net_profit   = 10000 + 500 - 6000 - 2000 - 1000 = 1500
                {
                    "journal_id": cls.journal.id,
                    "date": "2024-03-15",
                    "line_ids": [
                        (0, 0, {"account_id": cls.acc_ar.id, "debit": 10000.0}),
                        (0, 0, {"account_id": cls.acc_revenue.id, "credit": 10000.0}),
                        (0, 0, {"account_id": cls.acc_cogs.id, "debit": 6000.0}),
                        (0, 0, {"account_id": cls.acc_cash.id, "credit": 6000.0}),
                        (0, 0, {"account_id": cls.acc_cash.id, "debit": 500.0}),
                        (0, 0, {"account_id": cls.acc_other_inc.id, "credit": 500.0}),
                    ],
                },
                # Entry 3: equipment $20k (loan $15k + cash $5k),
                #          opex $2k, depreciation $1k
                {
                    "journal_id": cls.journal.id,
                    "date": "2024-06-30",
                    "line_ids": [
                        (0, 0, {"account_id": cls.acc_equipment.id, "debit": 20000.0}),
                        (0, 0, {"account_id": cls.acc_loan.id, "credit": 15000.0}),
                        (0, 0, {"account_id": cls.acc_cash.id, "credit": 5000.0}),
                        (0, 0, {"account_id": cls.acc_opex.id, "debit": 2000.0}),
                        (0, 0, {"account_id": cls.acc_cash.id, "credit": 2000.0}),
                        (0, 0, {"account_id": cls.acc_dep.id, "debit": 1000.0}),
                        (0, 0, {"account_id": cls.acc_accum_dep.id, "credit": 1000.0}),
                    ],
                },
            ]
        )
        entries.action_post()

    # ── helpers ───────────────────────────────────────────────────────

    def _instance(self, report_xmlid):
        return self.env["mis.report.instance"].create(
            {
                "name": "Test instance",
                "report_id": self.env.ref(report_xmlid).id,
                "period_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "FY2024",
                            "mode": "fix",
                            "manual_date_from": "2024-01-01",
                            "manual_date_to": "2024-12-31",
                        },
                    )
                ],
            }
        )

    def _body(self, report_xmlid):
        result = self._instance(report_xmlid).compute()
        return {r["row_id"]: r for r in result["body"]}

    def _val(self, body, row_id):
        row = body.get(row_id)
        if not row or not row.get("cells"):
            return None
        return row["cells"][0].get("val")

    # ── structure tests ───────────────────────────────────────────────

    def test_pl_kpis_present(self):
        """US P&L has all 9 GAAP KPIs including the COGS/Gross Profit split."""
        report = self.env.ref("l10n_us_mis_financial_report.report_pl_us")
        names = report.kpi_ids.mapped("name")
        for kpi in (
            "net_profit",
            "income",
            "gross_profit",
            "op_inc",
            "cost_of_reven",
            "other_inc",
            "expenses_total",
            "expenses",
            "depreciation",
        ):
            self.assertIn(kpi, names, f"Missing KPI: {kpi}")

    def test_bs_kpis_present(self):
        """US Balance Sheet has the full 24-KPI GAAP layout."""
        report = self.env.ref("l10n_us_mis_financial_report.report_bs_us")
        self.assertEqual(len(report.kpi_ids), 24)

    # ── computed-value tests ──────────────────────────────────────────

    def test_gross_profit(self):
        """Gross Profit = Operating Income − Cost of Revenue = 4 000."""
        body = self._body("l10n_us_mis_financial_report.report_pl_us")
        self.assertAlmostEqual(self._val(body, "op_inc"), 10000.0)
        self.assertAlmostEqual(self._val(body, "cost_of_reven"), 6000.0)
        self.assertAlmostEqual(self._val(body, "gross_profit"), 4000.0)

    def test_net_profit(self):
        """Net Profit = 10 000 + 500 − 6 000 − 2 000 − 1 000 = 1 500."""
        body = self._body("l10n_us_mis_financial_report.report_pl_us")
        self.assertAlmostEqual(self._val(body, "net_profit"), 1500.0)

    def test_other_income(self):
        """Other Income (interest) is captured as a distinct GAAP line."""
        body = self._body("l10n_us_mis_financial_report.report_pl_us")
        self.assertAlmostEqual(self._val(body, "other_inc"), 500.0)

    def test_depreciation(self):
        """Depreciation is separated from general Expenses."""
        body = self._body("l10n_us_mis_financial_report.report_pl_us")
        self.assertAlmostEqual(self._val(body, "depreciation"), 1000.0)
        self.assertAlmostEqual(self._val(body, "expenses"), 2000.0)

    def test_bs_fixed_assets_and_noncurrent_liabilities(self):
        """Fixed assets and non-current liabilities render non-zero."""
        body = self._body("l10n_us_mis_financial_report.report_bs_us")
        # Equipment 20 000 − accum dep 1 000 = 19 000
        self.assertAlmostEqual(self._val(body, "fixed_assets"), 19000.0)
        # Long-term loan 15 000
        self.assertAlmostEqual(self._val(body, "non_current_liabilities"), 15000.0)
