# Copyright 2026 Binhex - Edilio Escalona Almira.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from .common import UsTaxBranchCommon


class TestBranchNexus(UsTaxBranchCommon):
    """A branch uses the nexus declared on itself or on any ancestor."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        tree = cls.root | cls.branch_a1 | cls.branch_a2
        # Only the root nexus in FL from the base fixtures, and no TX nexus
        # anywhere in the tree.
        cls.env["us.tax.nexus"].search(
            [
                ("company_id", "in", tree.ids),
                "|",
                ("state_id", "=", cls.tx.id),
                ("company_id", "!=", cls.root.id),
            ]
        ).write({"active": False})

    def test_branch_inherits_root_nexus(self):
        nexus = self.env["us.tax.nexus"]
        self.assertTrue(nexus.has_nexus(self.branch_a1.id, self.fl.id))
        order = self._create_order(self.branch_a1, self.partner_fl)
        order.action_calculate_us_tax()
        self.assertNotEqual(order.us_tax_source, "exempt_nexus")
        self.assertNotEqual(order.order_line.tax_id.amount, 0.0)

    def test_no_nexus_in_tree_is_exempt(self):
        # A nexus on a sibling branch is not inherited.
        self.env["us.tax.nexus"].create(
            {"company_id": self.branch_a2.id, "state_id": self.tx.id}
        )
        nexus = self.env["us.tax.nexus"]
        self.assertFalse(nexus.has_nexus(self.branch_a1.id, self.tx.id))
        self.assertFalse(nexus.has_nexus(self.root.id, self.tx.id))
        order = self._create_order(self.branch_a1, self.partner_tx)
        order.action_calculate_us_tax()
        self.assertEqual(order.us_tax_source, "exempt_nexus")
        self.assertEqual(order.order_line.tax_id.name, "US Sales Tax - Exempt (0%)")

    def test_branch_own_nexus(self):
        # A nexus on the branch alone covers the branch, not its parent.
        self.env["us.tax.nexus"].create(
            {"company_id": self.branch_a1.id, "state_id": self.tx.id}
        )
        nexus = self.env["us.tax.nexus"]
        self.assertTrue(nexus.has_nexus(self.branch_a1.id, self.tx.id))
        self.assertFalse(nexus.has_nexus(self.root.id, self.tx.id))
        branch_order = self._create_order(self.branch_a1, self.partner_tx)
        branch_order.action_calculate_us_tax()
        self.assertNotEqual(branch_order.us_tax_source, "exempt_nexus")
        self.assertEqual(branch_order.order_line.tax_id.amount, 8.25)
        root_order = self._create_order(self.root, self.partner_tx)
        root_order.action_calculate_us_tax()
        self.assertEqual(root_order.us_tax_source, "exempt_nexus")
