# Copyright (C) 2019 Odoo GAP
# Copyright (C) 2019 Open Source Integrators
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

_logger = logging.getLogger("us_gaap")


@tagged("post_install")
class TestChartAcount(TransactionCase):
    def with_context(self, *args, **kwargs):
        context = dict(args[0] if args else self.env.context, **kwargs)
        self.env = self.env(context=context)
        return self

    def test_basic(self):
        _logger.debug("Creating chart of account")
        self.company = self.env["res.company"].create({"name": "US test company"})
        chart_us = self.env.ref("l10n_us_gaap.l10n_us_gaap_chart_template")
        self.env.ref("base.group_multi_company").write({"users": [(4, self.env.uid)]})
        self.env.user.write(
            {"company_ids": [(4, self.company.id)], "company_id": self.company.id}
        )
        chart_us.with_company(self.company).try_loading(
            company=self.company, install_demo=False
        )
        account_model = self.env["account.account"].with_company(self.company)
        bank_account = account_model.search(
            [("code", "=", "111101"), ("company_id", "=", self.company.id)]
        )
        liquidity_transfer = account_model.search(
            [("code", "=", "111901"), ("company_id", "=", self.company.id)]
        )
        finished_goods = account_model.search(
            [("code", "=", "133000"), ("company_id", "=", self.company.id)]
        )
        self.assertEqual(bank_account.name, "Bank Suspense Account")
        self.assertEqual(liquidity_transfer.name, "Liquidity Transfer")
        self.assertEqual(finished_goods.name, "Finished Goods")
