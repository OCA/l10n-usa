# Copyright 2025 Binhex - Simple Solutions
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from odoo.tests import tagged

from .common import BillcomTestCommon


@tagged("post_install", "-at_install", "billcom")
class TestBillcomService(BillcomTestCommon):
    """Tests for billcom.service core methods"""

    @classmethod
    def setUpClass(cls, chart_template_ref=None):
        super().setUpClass(chart_template_ref=chart_template_ref)

        # Create funding account for payment tests
        cls.funding_account = cls.env["billcom.funding.account"].create(
            {
                "billcom_id": "funding_acc_123",
                "account_type": "CHECKING",
                "is_default_payables": True,
            }
        )

    # ===== sync_partner Tests =====

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_sync_partner_vendor_create_success(self, mock_request):
        """Should create new vendor in Bill.com"""
        mock_request.return_value = {
            "id": "vendor_new_123",
            "name": "New Test Vendor",
            "email": "newvendor@test.com",
        }

        # Create vendor without billcom_id
        vendor = self.env["res.partner"].create(
            {
                "name": "New Test Vendor",
                "supplier_rank": 1,
                "is_sync_to_billcom": True,
                "email": "newvendor@test.com",
            }
        )

        service = self.env["billcom.service"]
        result = service.sync_partner(vendor, partner_type="vendor")

        self.assertTrue(result)
        self.assertEqual(vendor.billcom_id, "vendor_new_123")
        self.assertTrue(vendor.last_sync_date)

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_sync_partner_vendor_update_success(self, mock_request):
        """Should update existing vendor in Bill.com"""
        mock_request.return_value = {
            "id": "test_vendor_123",
            "name": "Test Vendor Bill.com Updated",
        }

        # Update vendor name
        self.vendor_billcom.name = "Test Vendor Bill.com Updated"

        service = self.env["billcom.service"]
        result = service.sync_partner(self.vendor_billcom, partner_type="vendor")

        self.assertTrue(result)
        self.assertTrue(self.vendor_billcom.last_sync_date)

    def test_sync_partner_not_marked_for_sync(self):
        """Should return False if partner not marked for sync"""
        vendor = self.env["res.partner"].create(
            {
                "name": "No Sync Vendor",
                "supplier_rank": 1,
                "is_sync_to_billcom": False,  # Not marked for sync
            }
        )

        service = self.env["billcom.service"]
        result = service.sync_partner(vendor, partner_type="vendor")

        self.assertFalse(result)

    # ===== get_funding_accounts Tests =====
    # Note: sync_item tests removed as product.product sync is not implemented in this module

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_get_funding_accounts_success(self, mock_request):
        """Should retrieve funding accounts from Bill.com"""
        mock_request.return_value = {
            "results": [
                {
                    "id": "funding_001",
                    "bankName": "Primary Bank",
                    "type": "CHECKING",
                    "status": "VERIFIED",
                },
                {
                    "id": "funding_002",
                    "bankName": "Credit Card",
                    "type": "CARD_ACCOUNT",
                    "status": "VERIFIED",
                },
            ]
        }

        service = self.env["billcom.service"]
        accounts = service.get_funding_accounts()

        self.assertTrue(accounts)
        self.assertEqual(len(accounts), 2)
        self.assertEqual(accounts[0]["id"], "funding_001")

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_get_default_funding_account_payables(self, mock_request):
        """Should return default payables funding account from API"""
        mock_request.return_value = {
            "results": [
                {
                    "id": "funding_001",
                    "bankName": "Primary Bank",
                    "status": "VERIFIED",
                    "default": {"payables": True, "receivables": False},
                },
                {
                    "id": "funding_002",
                    "bankName": "Secondary Bank",
                    "status": "VERIFIED",
                    "default": {"payables": False, "receivables": True},
                },
            ]
        }

        service = self.env["billcom.service"]
        account = service.get_default_funding_account(account_type="payables")

        self.assertTrue(account)
        self.assertEqual(account["id"], "funding_001")
        self.assertEqual(account["default"]["payables"], True)

    # ===== Status Mapping Tests =====

    def test_map_billcom_bill_status_to_odoo_state(self):
        """Should correctly map Bill.com bill statuses to Odoo states"""
        service = self.env["billcom.service"]

        # Test various status mappings to Odoo move state (draft/posted)
        # Only UNDEFINED maps to draft
        self.assertEqual(
            service._map_billcom_bill_status_to_odoo_state("UNDEFINED"), "draft"
        )

        # All other statuses map to posted
        self.assertEqual(
            service._map_billcom_bill_status_to_odoo_state("APPROVING"), "posted"
        )
        self.assertEqual(
            service._map_billcom_bill_status_to_odoo_state("SCHEDULED"), "posted"
        )
        self.assertEqual(
            service._map_billcom_bill_status_to_odoo_state("PAID"), "posted"
        )
        self.assertEqual(
            service._map_billcom_bill_status_to_odoo_state("CANCELLED"), "posted"
        )
        self.assertEqual(
            service._map_billcom_bill_status_to_odoo_state("VOID"), "posted"
        )
        # Unknown status defaults to posted (conservative approach)
        self.assertEqual(
            service._map_billcom_bill_status_to_odoo_state("UNKNOWN"), "posted"
        )

    def test_map_billcom_invoice_status_to_odoo_state(self):
        """Should correctly map Bill.com invoice statuses to Odoo states"""
        service = self.env["billcom.service"]

        # Test various status mappings to Odoo move state (draft/posted)
        # OPEN and UNDEFINED map to draft
        self.assertEqual(
            service._map_billcom_invoice_status_to_odoo_state("OPEN"), "draft"
        )
        self.assertEqual(
            service._map_billcom_invoice_status_to_odoo_state("UNDEFINED"), "draft"
        )

        # All other statuses map to posted
        self.assertEqual(
            service._map_billcom_invoice_status_to_odoo_state("PAID_IN_FULL"),
            "posted",
        )
        self.assertEqual(
            service._map_billcom_invoice_status_to_odoo_state("PARTIAL_PAYMENT"),
            "posted",
        )
        self.assertEqual(
            service._map_billcom_invoice_status_to_odoo_state("SCHEDULED"), "posted"
        )
        # Unknown status defaults to posted (conservative approach)
        self.assertEqual(
            service._map_billcom_invoice_status_to_odoo_state("UNKNOWN"), "posted"
        )

    def test_map_billcom_payment_status_to_odoo_state(self):
        """Should correctly map Bill.com payment statuses to Odoo states"""
        service = self.env["billcom.service"]

        # Test various status mappings to Odoo payment state (draft/posted)
        # UNDEFINED and UNPAID map to draft
        self.assertEqual(
            service._map_billcom_payment_status_to_odoo_state("UNDEFINED"), "draft"
        )
        self.assertEqual(
            service._map_billcom_payment_status_to_odoo_state("UNPAID"), "draft"
        )

        # All other statuses map to posted
        self.assertEqual(
            service._map_billcom_payment_status_to_odoo_state("PAID"), "posted"
        )
        self.assertEqual(
            service._map_billcom_payment_status_to_odoo_state("PARTIALLY_PAID"),
            "posted",
        )
        self.assertEqual(
            service._map_billcom_payment_status_to_odoo_state("SCHEDULED"), "posted"
        )
        self.assertEqual(
            service._map_billcom_payment_status_to_odoo_state("IN_PROCESS"), "posted"
        )
        self.assertEqual(
            service._map_billcom_payment_status_to_odoo_state("UNKNOWN"), "posted"
        )

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_sync_vendor_bank_account(self, mock_request):
        """Test syncing vendor bank account"""
        # Setup partner and bank
        partner = self.vendor_billcom
        bank = self.env["res.partner.bank"].create(
            {
                "acc_number": "123456789",
                "partner_id": partner.id,
                "bank_id": self.env["res.bank"]
                .create(
                    {
                        "name": "Test Bank",
                        "routing_number": "987654321",
                    }
                )
                .id,
            }
        )

        mock_request.side_effect = [
            [],  # Check existing
            {"id": "bank_123", "status": "VERIFIED"},  # Create
        ]

        service = self.env["billcom.service"]
        result = service.sync_vendor_bank_account(partner)

        self.assertTrue(result)
        self.assertEqual(bank.billcom_vendor_bank_id, "bank_123")
