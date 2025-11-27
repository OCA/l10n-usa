# Copyright 2025 Binhex - Simple Solutions
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import BillcomTestCommon


@tagged("post_install", "-at_install", "billcom")
class TestBillcomItem(BillcomTestCommon):
    """Tests for billcom.item model"""

    @classmethod
    def setUpClass(cls, chart_template_ref=None):
        super().setUpClass(chart_template_ref=chart_template_ref)

        # Create test tax
        cls.test_tax = cls.env["account.tax"].create(
            {
                "name": "Test Tax 10%",
                "amount": 10.0,
                "type_tax_use": "sale",
                "company_id": cls.env.company.id,
            }
        )

        # Create test Bill.com item
        cls.test_item = cls.env["billcom.item"].create(
            {
                "billcom_id": "00i123",
                "name": "Test Tax Item",
                "type": "SALES_TAX",
                "percentage": 10.0,
                "tax_ids": [(6, 0, [cls.test_tax.id])],
            }
        )

    # ===== Button Sync to Bill.com Tests =====

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_button_sync_to_billcom_create(self, mock_request):
        """Should create new item in Bill.com"""
        mock_request.return_value = {
            "id": "00i456",
            "name": "New Tax Item",
            "itemType": "SALES_TAX",
            "percentage": 15.0,
        }

        item = self.env["billcom.item"].create(
            {
                "name": "New Tax Item",
                "type": "SALES_TAX",
                "percentage": 15.0,
            }
        )

        item.button_sync_to_billcom()

        self.assertEqual(item.billcom_id, "00i456")
        mock_request.assert_called_once()

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_button_sync_to_billcom_update(self, mock_request):
        """Should update existing item in Bill.com"""
        mock_request.return_value = {
            "id": "00i123",
            "name": "Updated Tax Item",
            "itemType": "SALES_TAX",
            "percentage": 12.0,
        }

        self.test_item.name = "Updated Tax Item"
        self.test_item.percentage = 12.0
        self.test_item.button_sync_to_billcom()

        mock_request.assert_called_once()

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_button_sync_to_billcom_no_config(self, mock_request):
        """Should raise error if no Bill.com config"""
        # Deactivate config to trigger error
        self.billcom_config.active = False

        item = self.env["billcom.item"].create(
            {
                "name": "No Config Item",
                "type": "SALES_TAX",
                "percentage": 10.0,
            }
        )

        with self.assertRaises(UserError):
            item.button_sync_to_billcom()

        # Should not make request if config is missing
        mock_request.assert_not_called()

    # ===== Prepare Item Data Tests =====

    def test_prepare_item_data_sales_tax(self):
        """Should prepare data for SALES_TAX item"""
        data = self.test_item._prepare_item_data()

        self.assertEqual(data["name"], "Test Tax Item")
        self.assertEqual(data["itemType"], "SALES_TAX")
        self.assertEqual(data["percentage"], 10.0)
        self.assertIn("id", data)

    def test_prepare_item_data_new_item(self):
        """Should prepare data for new item without billcom_id"""
        item = self.env["billcom.item"].create(
            {
                "name": "New Item",
                "type": "SALES_TAX",
                "percentage": 8.0,
            }
        )

        data = item._prepare_item_data()

        self.assertEqual(data["name"], "New Item")
        self.assertNotIn("id", data)

    def test_prepare_item_data_archived(self):
        """Should include archived status"""
        self.test_item.active = False
        data = self.test_item._prepare_item_data()

        self.assertTrue(data.get("archived"))

    # ===== Sync from Odoo Taxes Tests =====

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_sync_from_odoo_taxes_create_new(self, mock_request):
        """Should create Bill.com items for Odoo taxes without items"""
        mock_request.return_value = {
            "id": "00i789",
            "name": "Tax 15%",
            "itemType": "SALES_TAX",
            "percentage": 15.0,
        }

        new_tax = self.env["account.tax"].create(
            {
                "name": "Tax 15%",
                "amount": 15.0,
                "type_tax_use": "sale",
                "company_id": self.env.company.id,
            }
        )

        self.env["billcom.item"].sync_from_odoo_taxes(self.billcom_config)

        item = self.env["billcom.item"].search(
            [
                ("tax_ids", "in", new_tax.id),
                ("billcom_config_id", "=", self.billcom_config.id),
            ]
        )
        self.assertTrue(item)
        self.assertEqual(item.billcom_id, "00i789")

    # @patch(
    #     "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    # )
    # def test_sync_from_odoo_taxes_skip_existing(self, mock_request):
    #     """Should skip taxes that already have Bill.com items"""
    #     initial_count = self.env["billcom.item"].search_count(
    #         [("tax_ids", "in", self.test_tax.id)]
    #     )

    #     self.env["billcom.item"].sync_from_odoo_taxes()

    #     final_count = self.env["billcom.item"].search_count(
    #         [("tax_ids", "in", self.test_tax.id)]
    #     )
    #     self.assertEqual(initial_count, final_count)

    # @patch(
    #     "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    # )
    # def test_sync_from_odoo_taxes_only_sale_taxes(self, mock_request):
    #     """Should only sync sale taxes"""
    #     purchase_tax = self.env["account.tax"].create(
    #         {
    #             "name": "Purchase Tax",
    #             "amount": 5.0,
    #             "type_tax_use": "purchase",
    #             "company_id": self.env.company.id,
    #         }
    #     )

    #     self.env["billcom.item"].sync_from_odoo_taxes(self.billcom_config)

    #     item = self.env["billcom.item"].search(
    #         [
    #             ("tax_ids", "in", purchase_tax.id),
    #         ]
    #     )
    #     self.assertFalse(item)

    # ===== Get Item for Tax Tests =====

    def test_get_item_for_tax_existing(self):
        """Should return existing Bill.com item for tax"""
        item_id = self.env["billcom.item"].get_item_for_tax(
            self.test_tax, self.billcom_config
        )

        self.assertEqual(item_id, "00i123")

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_get_item_for_tax_create_if_missing(self, mock_request):
        """Should create item if none exists for tax"""
        mock_request.return_value = {
            "id": "00i999",
            "name": "New Tax Item",
            "itemType": "SALES_TAX",
            "percentage": 20.0,
        }

        new_tax = self.env["account.tax"].create(
            {
                "name": "New Tax 20%",
                "amount": 20.0,
                "type_tax_use": "sale",
                "company_id": self.env.company.id,
            }
        )

        item_id = self.env["billcom.item"].get_item_for_tax(
            new_tax, self.billcom_config
        )

        self.assertEqual(item_id, "00i999")
        item = self.env["billcom.item"].search(
            [
                ("tax_ids", "in", new_tax.id),
                ("billcom_config_id", "=", self.billcom_config.id),
            ]
        )
        self.assertTrue(item)

    def test_get_item_for_tax_no_billcom_id(self):
        """Should return False if item exists but has no billcom_id"""
        self.env["billcom.item"].create(
            {
                "name": "Item without ID",
                "type": "SALES_TAX",
                "percentage": 5.0,
                "tax_ids": [(6, 0, [self.test_tax.id])],
            }
        )
        # Remove existing item with billcom_id
        self.test_item.unlink()

        item_id = self.env["billcom.item"].get_item_for_tax(
            self.test_tax, self.billcom_config
        )

        self.assertFalse(item_id)

    # ===== CRUD and Validation Tests =====

    def test_create_item_basic(self):
        """Should create basic item"""
        item = self.env["billcom.item"].create(
            {
                "name": "Basic Item",
                "type": "SALES_TAX",
                "percentage": 5.0,
            }
        )

        self.assertEqual(item.name, "Basic Item")
        self.assertEqual(item.type, "SALES_TAX")
        self.assertEqual(item.percentage, 5.0)

    def test_item_name_get(self):
        """Should return proper display name"""
        name = self.test_item.name_get()[0][1]

        self.assertIn("Test Tax Item", name)
        self.assertIn("10.0%", name)

    def test_item_unlink(self):
        """Should allow deletion of items"""
        item = self.env["billcom.item"].create(
            {
                "name": "Delete Me",
                "type": "SALES_TAX",
                "percentage": 3.0,
            }
        )

        item_id = item.id
        item.unlink()

        self.assertFalse(self.env["billcom.item"].search([("id", "=", item_id)]))

    def test_item_active_toggle(self):
        """Should toggle active status"""
        self.assertTrue(self.test_item.active)

        self.test_item.active = False
        self.assertFalse(self.test_item.active)

        self.test_item.active = True
        self.assertTrue(self.test_item.active)

    def test_search_by_billcom_id(self):
        """Should search items by Bill.com ID"""
        items = self.env["billcom.item"].search([("billcom_id", "=", "00i123")])

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0], self.test_item)

    def test_search_by_tax(self):
        """Should search items by Odoo tax"""
        items = self.env["billcom.item"].search([("tax_ids", "in", self.test_tax.id)])

        self.assertIn(self.test_item, items)
