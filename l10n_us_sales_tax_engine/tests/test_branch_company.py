# Copyright 2026 Binhex - Edilio Escalona Almira.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo.fields import Command
from odoo.tests import new_test_user

from .common import UsTaxBaseTest


class TestBranchCompany(UsTaxBaseTest):
    """Taxes created by the engine must be usable across a company tree."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.env["ir.config_parameter"].sudo().set_param(
            "l10n_us_tax.engine_mode", "local"
        )
        cls.root = cls.env.company
        cls.branch = cls.env["res.company"].create(
            {"name": "US Tax Branch", "parent_id": cls.root.id}
        )
        cls.other_root = cls.env["res.company"].create(
            {"name": "US Tax Other Root", "country_id": cls.us.id}
        )
        cls.env["us.tax.nexus"].create(
            [
                {"company_id": cls.branch.id, "state_id": cls.fl.id},
                {"company_id": cls.other_root.id, "state_id": cls.fl.id},
            ]
        )
        # Dedicated ZIP with a rate no other record uses, so the tax for it
        # never exists before the test runs.
        jurisdiction = cls.env["us.tax.jurisdiction"].create(
            {
                "name": "Branch Test County",
                "type": "county",
                "state_id": cls.fl.id,
                "county": "BRANCH TEST",
            }
        )
        cls.env["us.tax.rate"].create(
            {
                "jurisdiction_id": jurisdiction.id,
                "product_tax_category_id": cls.cat_tangible.id,
                "state_rate": 0.06,
                "county_rate": 0.0025,
                "effective_date": "2020-01-01",
                "source": "test",
            }
        )
        cls.env["us.tax.zip.mapping"].create(
            {
                "zip": "32999",
                "state_id": cls.fl.id,
                "jurisdiction_id": jurisdiction.id,
                "county": "BRANCH TEST",
                "confidence": 1.0,
                "source": "test",
            }
        )
        cls.partner_new_rate = cls.env["res.partner"].create(
            {
                "name": "Branch Test Customer",
                "zip": "32999",
                "city": "Branch City",
                "state_id": cls.fl.id,
                "country_id": cls.us.id,
            }
        )
        cls.partner_exempt = cls.env["res.partner"].create(
            {
                "name": "Branch Exempt Customer",
                "zip": "33101",
                "city": "Miami",
                "state_id": cls.fl.id,
                "country_id": cls.us.id,
                "us_tax_exempt": True,
            }
        )
        cls.salesman = new_test_user(
            cls.env,
            login="us_tax_branch_salesman",
            groups="sales_team.group_sale_salesman",
            company_id=cls.branch.id,
            company_ids=[Command.set((cls.root | cls.branch | cls.other_root).ids)],
        )

    def _calculate_order(self, company, partner):
        order = (
            self.env["sale.order"]
            .with_user(self.salesman)
            .with_company(company)
            .create(
                {
                    "company_id": company.id,
                    "partner_id": partner.id,
                    "order_line": [
                        Command.create(
                            {
                                "product_id": self.product.id,
                                "product_uom_qty": 1.0,
                                "price_unit": 100.0,
                            }
                        )
                    ],
                }
            )
        )
        order.action_calculate_us_tax()
        return order

    def test_branch_order_reuses_root_tax(self):
        root_order = self._calculate_order(self.root, self.partner_fl)
        branch_order = self._calculate_order(self.branch, self.partner_fl)
        root_tax = root_order.order_line.tax_id
        self.assertTrue(root_tax)
        self.assertEqual(branch_order.order_line.tax_id, root_tax)

    def test_branch_order_creates_tax_in_root(self):
        order = self._calculate_order(self.branch, self.partner_new_rate)
        tax = order.order_line.tax_id
        self.assertEqual(tax.name, "US Sales Tax FL 6.25%")
        self.assertEqual(tax.company_id, self.root)

    def test_branch_exempt_tax_in_root(self):
        order = self._calculate_order(self.branch, self.partner_exempt)
        tax = order.order_line.tax_id
        self.assertEqual(tax.name, "US Sales Tax - Exempt (0%)")
        self.assertEqual(tax.company_id, self.root)

    def test_tax_group_from_document_root(self):
        self._calculate_order(self.root, self.partner_fl)
        order = self._calculate_order(self.other_root, self.partner_fl)
        tax = order.order_line.tax_id
        self.assertEqual(tax.company_id, self.other_root)
        self.assertEqual(tax.tax_group_id.company_id, self.other_root)
