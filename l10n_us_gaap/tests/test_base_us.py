# Copyright (C) 2019 Odoo GAP
# Copyright (C) 2019 Open Source Integrators
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from odoo.tests.common import TransactionCase

_logger = logging.getLogger("us_gaap")


class TestChartAcount(TransactionCase):
    def with_context(self, *args, **kwargs):
        context = dict(args[0] if args else self.env.context, **kwargs)
        self.env = self.env(context=context)
        return self

    def test_basic(self):
        _logger.debug("Creating chart of account")
        self.company = self.env["res.company"].create({"name": "US test company"})
        self.env.ref("base.group_multi_company").write({"users": [(4, self.env.uid)]})
        self.env.user.write(
            {"company_ids": [(4, self.company.id)], "company_id": self.company.id}
        )
        self.env["account.chart.template"].try_loading(
            template_code="us_gaap", company=self.company, install_demo=False
        )
        self.with_context(company_id=self.company.id, force_company=self.company.id)
        bank_account = self.env["account.account"].search(
            [("code", "=", "111102"), ("company_id", "=", self.company.id)]
        )
        liquidity_transfer = self.env["account.account"].search(
            [("code", "=", "111701"), ("company_id", "=", self.company.id)]
        )
        finished_goods = self.env["account.account"].search(
            [("code", "=", "133000"), ("company_id", "=", self.company.id)]
        )
        self.assertEqual(bank_account.name, "Bank Suspense Account")
        self.assertEqual(liquidity_transfer.name, "Liquidity Transfer")
        self.assertEqual(finished_goods.name, "Finished Goods")
