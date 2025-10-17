# Copyright 2025 Binhex - Simple Solutions
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
from unittest.mock import patch

from odoo.tests import tagged

from .common import BillcomTestCommon

_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install", "billcom")
class TestVendorBankSync(BillcomTestCommon):
    """Test vendor bank account synchronization with Bill.com"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Create US bank for vendor
        cls.us_bank = cls.env["res.partner.bank"].create(
            {
                "partner_id": cls.vendor_billcom.id,
                "acc_number": "123456789",
                "aba_routing": "021000021",
                "acc_holder_name": "Test Vendor LLC",
            }
        )

        # Create international vendor with bank
        cls.intl_vendor = cls.env["res.partner"].create(
            {
                "name": "International Vendor",
                "supplier_rank": 1,
                "billcom_id": "intl_vendor_001",
                "country_id": cls.env.ref("base.uk").id,
            }
        )

        # International bank info with SWIFT
        cls.intl_bank_info = cls.env["res.bank"].create(
            {
                "name": "International Bank",
                "bic": "DEUTDEFF",
                "street": "Bank Street 1",
                "city": "London",
            }
        )

        # International bank account
        cls.intl_bank_account = cls.env["res.partner.bank"].create(
            {
                "partner_id": cls.intl_vendor.id,
                "acc_number": "GB29NWBK60161331926819",
                "bank_id": cls.intl_bank_info.id,
            }
        )

    # ===== Tests de Validación =====

    def test_sync_vendor_bank_no_partner(self):
        """Should return False if no partner provided"""
        service = self.env["billcom.service"]
        result = service.sync_vendor_bank_account(None)
        self.assertFalse(result)

    def test_sync_vendor_bank_no_billcom_id(self):
        """Should return False if partner has no billcom_id"""
        vendor = (
            self.env["res.partner"]
            .with_context(skip_billcom_sync=True)
            .create(
                {
                    "name": "No ID Vendor",
                    "supplier_rank": 1,
                }
            )
        )
        # Add bank account
        self.env["res.partner.bank"].with_context(skip_billcom_sync=True).create(
            {
                "partner_id": vendor.id,
                "acc_number": "987654321",
                "aba_routing": "021000021",
            }
        )
        service = self.env["billcom.service"]
        result = service.sync_vendor_bank_account(vendor)
        self.assertFalse(result)

    def test_sync_vendor_bank_not_vendor(self):
        """Should return False if partner is not a vendor"""
        customer = self.customer_billcom
        customer.supplier_rank = 0  # Ensure NOT a vendor
        # Add bank account
        self.env["res.partner.bank"].with_context(skip_billcom_sync=True).create(
            {
                "partner_id": customer.id,
                "acc_number": "555666777",
                "aba_routing": "021000021",
            }
        )
        service = self.env["billcom.service"]
        result = service.sync_vendor_bank_account(customer)
        self.assertFalse(result)

    def test_sync_vendor_bank_no_bank_accounts(self):
        """Should return False if vendor has no bank accounts"""
        vendor = (
            self.env["res.partner"]
            .with_context(skip_billcom_sync=True)
            .create(
                {
                    "name": "No Bank Vendor",
                    "supplier_rank": 1,
                    "billcom_id": "vendor_no_bank",
                }
            )
        )
        service = self.env["billcom.service"]
        result = service.sync_vendor_bank_account(vendor)
        self.assertFalse(result)

    def test_sync_vendor_bank_no_account_number(self):
        """Should return False if bank has no account number"""
        vendor = self.vendor_billcom
        bank = (
            self.env["res.partner.bank"]
            .with_context(skip_billcom_sync=True)
            .create(
                {
                    "partner_id": vendor.id,
                    "acc_number": "",  # Empty
                }
            )
        )
        # Replace vendor banks with this one
        vendor.with_context(skip_billcom_sync=True).write(
            {"bank_ids": [(6, 0, [bank.id])]}
        )
        service = self.env["billcom.service"]
        result = service.sync_vendor_bank_account(vendor)
        self.assertFalse(result)

    def test_sync_vendor_bank_us_no_routing(self):
        """Should return False if US bank has no routing number"""
        vendor = self.vendor_billcom
        bank = (
            self.env["res.partner.bank"]
            .with_context(skip_billcom_sync=True)
            .create(
                {
                    "partner_id": vendor.id,
                    "acc_number": "999888777",
                    "aba_routing": "",  # No routing
                }
            )
        )
        # Replace vendor banks with this one
        vendor.with_context(skip_billcom_sync=True).write(
            {"bank_ids": [(6, 0, [bank.id])]}
        )
        service = self.env["billcom.service"]
        result = service.sync_vendor_bank_account(vendor)
        self.assertFalse(result)

    # ===== Tests de Flujo Principal US =====

    @patch(
        "odoo.addons.billcom.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_sync_vendor_bank_us_checking_success(self, mock_request):
        """Should create US CHECKING bank account successfully"""

        # Mock: GET returns 404 (not exists), POST returns success
        def side_effect(endpoint, method="GET", **kwargs):
            if method == "GET":
                raise Exception("404 Not Found")
            elif method == "POST":
                return {
                    "id": "bank_account_123",
                    "status": "ACTIVE",
                    "accountNumber": "****6789",
                }

        mock_request.side_effect = side_effect

        service = self.env["billcom.service"]
        result = service.sync_vendor_bank_account(self.vendor_billcom)

        self.assertTrue(result)
        # Verify bank record was updated
        self.assertEqual(self.us_bank.billcom_vendor_bank_id, "bank_account_123")
        self.assertEqual(self.us_bank.billcom_account_status, "ACTIVE")
        self.assertIsNotNone(self.us_bank.billcom_last_sync_date)

    @patch(
        "odoo.addons.billcom.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_sync_vendor_bank_us_with_existing_delete_first(self, mock_request):
        """Should delete existing account before creating new one"""

        # Mock: GET returns existing, DELETE success, POST success
        call_count = {"get": 0, "delete": 0, "post": 0}

        def side_effect(endpoint, method="GET", **kwargs):
            if method == "GET":
                call_count["get"] += 1
                return {"id": "old_bank_123", "status": "ACTIVE"}
            elif method == "DELETE":
                call_count["delete"] += 1
                return True
            elif method == "POST":
                call_count["post"] += 1
                return {"id": "new_bank_456", "status": "ACTIVE"}

        mock_request.side_effect = side_effect

        service = self.env["billcom.service"]
        result = service.sync_vendor_bank_account(self.vendor_billcom)

        self.assertTrue(result)
        self.assertEqual(call_count["get"], 1)
        self.assertEqual(call_count["delete"], 1)
        self.assertEqual(call_count["post"], 1)
        self.assertEqual(self.us_bank.billcom_vendor_bank_id, "new_bank_456")

    # ===== Tests de Flujo Internacional =====

    # @patch(
    #     "odoo.addons.billcom.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    # )
    # def test_sync_vendor_bank_international_with_swift(self, mock_request):
    #     """Should include SWIFT/BIC for international banks"""

    #     def side_effect(endpoint, method="GET", data=None, **kwargs):
    #         if method == "GET":
    #             raise Exception("404 Not Found")
    #         elif method == "POST":
    #             # Verify payload includes bankInfo with SWIFT
    #             self.assertIn("bankInfo", data)
    #             self.assertEqual(data["bankInfo"]["swiftBIC"], "DEUTDEFF")
    #             self.assertEqual(data["bankInfo"]["countryISO"], "GB")
    #             return {"id": "intl_bank_789", "status": "ACTIVE"}

    #     mock_request.side_effect = side_effect

    #     service = self.env["billcom.service"]
    #     result = service.sync_vendor_bank_account(self.intl_vendor)

    #     self.assertTrue(result)
    #     self.assertEqual(self.intl_bank_account.billcom_vendor_bank_id, "intl_bank_789")

    # ===== Tests de Manejo de Errores =====

    # @patch(
    #     "odoo.addons.billcom.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    # )
    # def test_sync_vendor_bank_api_error_on_create(self, mock_request):
    #     """Should handle API errors when creating account"""

    #     def side_effect(endpoint, method="GET", **kwargs):
    #         if method == "GET":
    #             raise Exception("404 Not Found")
    #         elif method == "POST":
    #             raise Exception("API Error: Invalid account number")

    #     mock_request.side_effect = side_effect

    #     service = self.env["billcom.service"]
    #     result = service.sync_vendor_bank_account(self.vendor_billcom)

    #     self.assertFalse(result)

    @patch(
        "odoo.addons.billcom.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_sync_vendor_bank_delete_fails_continue_anyway(self, mock_request):
        """Should continue creation even if DELETE fails"""

        def side_effect(endpoint, method="GET", **kwargs):
            if method == "GET":
                return {"id": "old_bank", "status": "ACTIVE"}
            elif method == "DELETE":
                raise Exception("Delete failed")
            elif method == "POST":
                return {"id": "new_bank_999", "status": "ACTIVE"}

        mock_request.side_effect = side_effect

        service = self.env["billcom.service"]
        result = service.sync_vendor_bank_account(self.vendor_billcom)

        # Should succeed despite DELETE error
        self.assertTrue(result)
        self.assertEqual(self.us_bank.billcom_vendor_bank_id, "new_bank_999")

    # ===== Tests de Actualización de Datos =====

    @patch(
        "odoo.addons.billcom.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_sync_vendor_bank_posts_to_chatter(self, mock_request):
        """Should post message to partner chatter"""

        def side_effect(*args, **kwargs):
            # Get method from args or kwargs
            method = kwargs.get("method", args[1] if len(args) > 1 else "GET")
            if method == "GET":
                raise Exception("404 Not Found")
            elif method == "POST":
                return {"id": "bank_chatter_123", "status": "ACTIVE"}
            return {}

        mock_request.side_effect = side_effect

        # Count messages before
        messages_before = len(self.vendor_billcom.message_ids)

        service = self.env["billcom.service"]
        result = service.sync_vendor_bank_account(self.vendor_billcom)

        self.assertTrue(result)
        # Should have new message in chatter
        messages_after = len(self.vendor_billcom.message_ids)
        self.assertGreater(messages_after, messages_before)

        # Verify message content
        last_message = self.vendor_billcom.message_ids[0]
        self.assertIn("Bank Account Synced", last_message.body)
        self.assertIn("bank_chatter_123", last_message.body)
