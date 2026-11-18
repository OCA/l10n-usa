# Copyright 2026 Binhex - Edilio Escalona Almira.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo.exceptions import AccessError
from odoo.fields import Command
from odoo.tests import new_test_user

from .common import UsTaxBaseTest


class TestNexusParent(UsTaxBaseTest):
    """A branch collects tax where it or any of its parent companies has nexus.

    The root is the test company, with the FL nexus of the base fixtures. The
    tree is root -> branch -> sub-branch, plus a sibling of the branch.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.env["ir.config_parameter"].sudo().set_param(
            "l10n_us_tax.engine_mode", "local"
        )
        cls.root = cls.env.company
        companies = cls.env["res.company"]
        cls.branch = companies.create(
            {"name": "US Tax Nexus Branch", "parent_id": cls.root.id}
        )
        cls.sub_branch = companies.create(
            {"name": "US Tax Nexus Sub-branch", "parent_id": cls.branch.id}
        )
        cls.sibling = companies.create(
            {"name": "US Tax Nexus Sibling", "parent_id": cls.root.id}
        )
        cls.nexus = cls.env["us.tax.nexus"]
        # A salesman of the sub-branch alone, with no access to any nexus.
        cls.salesman = new_test_user(
            cls.env,
            login="us_tax_sub_branch_salesman",
            groups="sales_team.group_sale_salesman",
            company_id=cls.sub_branch.id,
            company_ids=[Command.set(cls.sub_branch.ids)],
        )

    def test_nexus_inherited_at_any_depth(self):
        self.assertTrue(self.nexus.has_nexus(self.branch.id, self.fl.id))
        self.assertTrue(self.nexus.has_nexus(self.sub_branch.id, self.fl.id))

    def test_nexus_not_inherited_upwards_or_sideways(self):
        self.nexus.create({"company_id": self.branch.id, "state_id": self.ny.id})
        self.assertTrue(self.nexus.has_nexus(self.branch.id, self.ny.id))
        self.assertTrue(self.nexus.has_nexus(self.sub_branch.id, self.ny.id))
        self.assertFalse(self.nexus.has_nexus(self.root.id, self.ny.id))
        self.assertFalse(self.nexus.has_nexus(self.sibling.id, self.ny.id))

    def test_sub_branch_user_sees_inherited_nexus(self):
        sibling_nexus = self.nexus.create(
            {"company_id": self.sibling.id, "state_id": self.ny.id}
        )
        root_nexus = self.nexus.search([("company_id", "=", self.root.id)])
        tax_user = new_test_user(
            self.env,
            login="us_tax_sub_branch_tax_user",
            groups="l10n_us_sales_tax_engine.group_us_tax_user",
            company_id=self.sub_branch.id,
            company_ids=[Command.set(self.sub_branch.ids)],
        )
        visible = self.nexus.with_user(tax_user).search([])
        self.assertTrue(root_nexus)
        self.assertEqual(visible & root_nexus, root_nexus)
        self.assertFalse(visible & sibling_nexus)

    def test_sub_branch_manager_only_changes_own_nexus(self):
        root_nexus = self.nexus.search(
            [("company_id", "=", self.root.id), ("state_id", "=", self.fl.id)]
        )
        tax_manager = new_test_user(
            self.env,
            login="us_tax_sub_branch_tax_manager",
            groups="l10n_us_sales_tax_engine.group_us_tax_manager",
            company_id=self.sub_branch.id,
            company_ids=[Command.set(self.sub_branch.ids)],
        )
        nexus = self.nexus.with_user(tax_manager)
        own_nexus = nexus.create(
            {"company_id": self.sub_branch.id, "state_id": self.ny.id}
        )
        own_nexus.write({"threshold_amount": 100000.0})
        self.assertEqual(own_nexus.threshold_amount, 100000.0)
        inherited = nexus.browse(root_nexus.id)
        self.assertEqual(inherited.state_id, self.fl)
        with self.assertRaises(AccessError):
            inherited.write({"threshold_amount": 100000.0})
        with self.assertRaises(AccessError):
            inherited.unlink()

    def test_archived_parent_nexus_not_inherited(self):
        self.nexus.search(
            [("company_id", "=", self.root.id), ("state_id", "=", self.fl.id)]
        ).active = False
        self.assertFalse(self.nexus.has_nexus(self.sub_branch.id, self.fl.id))

    def test_sub_branch_order_taxed_by_root_nexus(self):
        order = (
            self.env["sale.order"]
            .with_user(self.salesman)
            .with_company(self.sub_branch)
            .create(
                {
                    "company_id": self.sub_branch.id,
                    "partner_id": self.partner_fl.id,
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
        self.assertEqual(order.us_tax_source, "local")
        self.assertEqual(order.order_line.tax_id.name, "US Sales Tax FL 7%")
