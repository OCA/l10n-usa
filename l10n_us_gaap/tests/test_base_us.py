# Copyright (C) 2019 Odoo GAP
# Copyright (C) 2019 Open Source Integrators
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from odoo.tests.common import TransactionCase

_logger = logging.getLogger("us_gaap")


class TestChartAcount(TransactionCase):
    def test_basic(self):
        _logger.debug("Creating chart of account")
        self.company = self.env.ref("l10n_us_gaap.demo_company_us_gaap")
        bank_account = (
            self.env["account.account"]
            .with_company(self.company)
            .search([("code", "=", "111102"), ("company_ids", "in", self.company.ids)])
        )
        liquidity_transfer = (
            self.env["account.account"]
            .with_company(self.company)
            .search([("code", "=", "111701"), ("company_ids", "in", self.company.ids)])
        )
        finished_goods = (
            self.env["account.account"]
            .with_company(self.company)
            .search([("code", "=", "133000"), ("company_ids", "in", self.company.ids)])
        )
        self.assertEqual(bank_account.name, "Bank Suspense Account")
        self.assertEqual(liquidity_transfer.name, "Liquidity Transfer")
        self.assertEqual(finished_goods.name, "Finished Goods")
