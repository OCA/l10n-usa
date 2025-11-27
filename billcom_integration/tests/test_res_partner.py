# Copyright 2025 Binhex - Simple Solutions
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import BillcomTestCommon

_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install", "billcom")
class TestResPartner(BillcomTestCommon):
    """Test res.partner Bill.com integration"""

    def test_partner_billcom_fields(self):
        """Test that partner has all required Bill.com fields"""
        required_fields = [
            "billcom",
            "billcom_id",
            "is_sync_to_billcom",
            "billcom_sync_status",
            "billcom_sync_error",
            "last_sync_date",
            "billcom_res_currency_id",
            "billcom_sync_state",
            "billcom_payment_purpose_id",
        ]

        for field in required_fields:
            self.assertTrue(
                hasattr(self.vendor_billcom, field),
                f"Partner should have field: {field}",
            )

    def test_prepare_partner_data_vendor(self):
        """Test _prepare_partner_data for vendor"""
        partner_data = self.vendor_billcom._prepare_partner_data(partner_type="vendor")

        self.assertIsNotNone(partner_data)
        self.assertEqual(partner_data["name"], "Test Vendor Bill.com")
        self.assertEqual(partner_data["email"], "vendor@test.com")
        self.assertEqual(partner_data["phone"], "+1-555-123-4567")

        # Check address structure
        self.assertIn("mailingAddress", partner_data)
        address = partner_data["mailingAddress"]
        self.assertEqual(address["line1"], "123 Test Street")
        self.assertEqual(address["city"], "Test City")
        self.assertEqual(address["zipOrPostalCode"], "12345")

    def test_prepare_partner_data_customer(self):
        """Test _prepare_partner_data for customer"""
        partner_data = self.customer_billcom._prepare_partner_data(
            partner_type="customer"
        )

        self.assertIsNotNone(partner_data)
        self.assertEqual(partner_data["name"], "Test Customer Bill.com")
        self.assertIn("mailingAddress", partner_data)

    def test_prepare_partner_data_not_synced(self):
        """Test _prepare_partner_data returns False for non-sync partners"""
        partner = self.env["res.partner"].create(
            {
                "name": "Non-Sync Partner",
                "is_sync_to_billcom": False,
            }
        )

        partner_data = partner._prepare_partner_data()
        self.assertFalse(partner_data)

    def test_currency_field_in_partner_data(self):
        """Test that billcom_res_currency_id is included in API data"""
        # Set EUR currency for non-US vendor
        eur = self.env["res.currency"].search([("name", "=", "EUR")], limit=1)
        if not eur:
            eur = self.env["res.currency"].create({"name": "EUR", "symbol": "€"})

        intl_vendor = self.env["res.partner"].create(
            {
                "name": "International Vendor",
                "supplier_rank": 1,
                "is_sync_to_billcom": True,
                "street": "456 Euro St",
                "city": "Paris",
                "zip": "75001",
                "country_id": self.env.ref("base.fr").id,  # France
                "billcom_res_currency_id": eur.id,
            }
        )

        partner_data = intl_vendor._prepare_partner_data(partner_type="vendor")
        self.assertEqual(partner_data.get("billCurrency"), "EUR")

    def test_currency_not_included_for_us_vendors(self):
        """Test that billCurrency is not sent for US vendors"""
        partner_data = self.vendor_billcom._prepare_partner_data(partner_type="vendor")

        # US vendors should not have billCurrency field
        self.assertNotIn("billCurrency", partner_data)

    def test_parent_child_partner_structure(self):
        """Test parent-child partner relationships for multi-currency"""
        # Create parent partner
        parent = self.env["res.partner"].create(
            {
                "name": "Parent Vendor Corp",
                "supplier_rank": 1,
                "is_company": True,
                "is_sync_to_billcom": True,
                "billcom_id": "parent_vendor_001",
            }
        )

        # Create children with different currencies
        usd = self.env["res.currency"].search([("name", "=", "USD")], limit=1)
        eur = self.env["res.currency"].search([("name", "=", "EUR")], limit=1)
        if not eur:
            eur = self.env["res.currency"].create({"name": "EUR", "symbol": "€"})

        child_usd = self.env["res.partner"].create(
            {
                "name": "Parent Vendor Corp",
                "parent_id": parent.id,
                "type": "contact",
                "billcom_res_currency_id": usd.id,
                "billcom_id": "child_vendor_usd",
            }
        )

        child_eur = self.env["res.partner"].create(
            {
                "name": "Parent Vendor Corp",
                "parent_id": parent.id,
                "type": "contact",
                "billcom_res_currency_id": eur.id,
                "billcom_id": "child_vendor_eur",
            }
        )

        # Verify parent-child relationships
        self.assertEqual(child_usd.parent_id, parent)
        self.assertEqual(child_eur.parent_id, parent)
        self.assertIn(child_usd, parent.child_ids)
        self.assertIn(child_eur, parent.child_ids)

        # Verify different currencies
        self.assertEqual(child_usd.billcom_res_currency_id.name, "USD")
        self.assertEqual(child_eur.billcom_res_currency_id.name, "EUR")

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service.BillcomService._make_request"  # noqa B950
    )
    def test_sync_to_billcom_vendor(self, mock_request):
        """Test syncing vendor to Bill.com"""
        # Mock API response
        mock_request.return_value = {
            "id": "vendor_abc123",
            "name": "Test Vendor Bill.com",
            "isActive": True,
        }

        # Trigger sync
        self.vendor_billcom.sync_to_billcom(partner_type="vendor")

        # Verify API was called
        mock_request.assert_called_once()

        # Verify billcom_id was updated
        self.assertEqual(self.vendor_billcom.billcom_id, "vendor_abc123")

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service.BillcomService._make_request"  # noqa B950
    )
    def test_sync_from_billcom_by_id(self, mock_request):
        """Test syncing partner from Bill.com by ID"""
        # Mock API response
        mock_request.return_value = {
            "id": "vendor_xyz789",
            "name": "New Vendor from Bill.com",
            "email": "newvendor@example.com",
            "phone": "+1-555-999-8888",
            "isActive": True,
            "address": {
                "line1": "789 New St",
                "city": "New City",
                "stateOrProvince": "CA",
                "zipOrPostalCode": "99999",
                "country": "US",
            },
            "billCurrency": "USD",
        }

        # Call sync_from_billcom_by_id
        partner = self.env["res.partner"].sync_from_billcom_by_id(
            billcom_id="vendor_xyz789", partner_type="vendor"
        )

        # Verify partner was created/updated
        self.assertIsNotNone(partner)
        self.assertEqual(partner.billcom_id, "vendor_xyz789")
        self.assertEqual(partner.name, "New Vendor from Bill.com")
        self.assertEqual(partner.email, "newvendor@example.com")

    def test_billcom_sync_status_field(self):
        """Test billcom_sync_status field values"""
        # Test default value
        new_partner = self.env["res.partner"].create(
            {
                "name": "Test Partner Status",
                "is_sync_to_billcom": True,
            }
        )

        self.assertEqual(new_partner.billcom_sync_status, "not_synced")

        # Test status changes
        new_partner.billcom_sync_status = "synced"
        self.assertEqual(new_partner.billcom_sync_status, "synced")

        new_partner.billcom_sync_status = "sync_failed"
        self.assertEqual(new_partner.billcom_sync_status, "sync_failed")

    def test_partner_address_formatting(self):
        """Test that partner addresses are formatted correctly for Bill.com"""
        # Create partner with complete address
        partner = self.env["res.partner"].create(
            {
                "name": "Address Test Partner",
                "supplier_rank": 1,
                "is_sync_to_billcom": True,
                "street": "123 Main St",
                "street2": "Suite 100",
                "city": "San Francisco",
                "state_id": self.env.ref("base.state_us_5").id,  # California
                "zip": "94105",
                "country_id": self.env.ref("base.us").id,
            }
        )

        partner_data = partner._prepare_partner_data(partner_type="vendor")
        address = partner_data["mailingAddress"]

        self.assertEqual(address["line1"], "123 Main St")
        self.assertEqual(address["line2"], "Suite 100")
        self.assertEqual(address["city"], "San Francisco")
        self.assertEqual(address["stateOrProvince"], "CA")
        self.assertEqual(address["zipOrPostalCode"], "94105")
        self.assertEqual(address["country"], "US")

    def test_partner_minimal_address(self):
        """Test partner with minimal required address fields"""
        partner = self.env["res.partner"].create(
            {
                "name": "Minimal Address Partner",
                "is_sync_to_billcom": True,
                # No street, city, or zip - should use defaults
            }
        )

        partner_data = partner._prepare_partner_data(partner_type="vendor")
        address = partner_data["mailingAddress"]

        # Should have default values
        self.assertEqual(address["line1"], "N/A")
        self.assertEqual(address["city"], "N/A")
        self.assertEqual(address["zipOrPostalCode"], "00000")
        self.assertEqual(address["country"], "US")

    def test_payment_purpose_field(self):
        """Test billcom_payment_purpose_id field"""
        # Create payment purpose
        purpose = self.env["billcom.payment.purpose"].create(
            {
                "name": "BUSINESS",
                "description": "Business Payment",
                "country_id": self.env.ref("base.us").id,
            }
        )

        partner = self.env["res.partner"].create(
            {
                "name": "Partner with Purpose",
                "supplier_rank": 1,
                "billcom_payment_purpose_id": purpose.id,
                "country_id": self.env.ref("base.us").id,
            }
        )

        self.assertEqual(partner.billcom_payment_purpose_id, purpose)

    def test_partner_bank_account_sync(self):
        """Test that partner bank accounts have Bill.com fields"""
        bank = self.env["res.partner.bank"].create(
            {
                "partner_id": self.vendor_billcom.id,
                "acc_number": "123456789",
                "aba_routing": "021000021",
            }
        )

        # Check if bank has billcom fields (from billcom.abstract.model)
        self.assertTrue(hasattr(bank, "billcom_id"))
        self.assertTrue(hasattr(bank, "is_sync_to_billcom"))

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service.BillcomService._make_request"  # noqa B950
    )
    def test_sync_error_handling(self, mock_request):
        """Test that sync errors are properly captured"""
        # Mock API error
        mock_request.side_effect = UserError("API Connection Failed")

        # Attempt sync
        with self.assertRaises(UserError):
            self.vendor_billcom.sync_to_billcom(partner_type="vendor")

    def test_archived_partner_sync(self):
        """Test syncing archived/inactive partners"""
        # Archive partner
        self.vendor_billcom.active = False

        partner_data = self.vendor_billcom._prepare_partner_data(partner_type="vendor")

        # Should still prepare data for archived partners
        self.assertIsNotNone(partner_data)

    def test_multiple_addresses_priority(self):
        """Test that invoice and delivery addresses are used when available"""
        # Create parent with child addresses
        parent = self.env["res.partner"].create(
            {
                "name": "Multi-Address Company",
                "is_company": True,
                "is_sync_to_billcom": True,
                "street": "100 Main Office",
                "city": "Office City",
                "zip": "10000",
                "country_id": self.env.ref("base.us").id,
            }
        )

        # Create invoice address
        self.env["res.partner"].create(
            {
                "name": "Billing Department",
                "parent_id": parent.id,
                "type": "invoice",
                "street": "200 Billing St",
                "city": "Billing City",
                "zip": "20000",
                "country_id": self.env.ref("base.us").id,
            }
        )

        # Create delivery address
        self.env["res.partner"].create(
            {
                "name": "Warehouse",
                "parent_id": parent.id,
                "type": "delivery",
                "street": "300 Warehouse Ave",
                "city": "Warehouse City",
                "zip": "30000",
                "country_id": self.env.ref("base.us").id,
            }
        )

        # Prepare data - should use child addresses
        partner_data = parent._prepare_partner_data(partner_type="vendor")

        # Billing address should be from invoice contact
        billing = partner_data.get("mailingAddress")
        self.assertEqual(billing["line1"], "200 Billing St")
        self.assertEqual(billing["city"], "Billing City")

        # Shipping address should be from delivery contact
        # Note: Bill.com API v3 uses 'shippingAddress' for customers, but for vendors
        # it typically only uses 'address' (mapped to mailingAddress in our logic).
        # However, if we were testing a customer, it would have shippingAddress.
        # Let's test as customer to verify shipping address logic
        customer_data = parent._prepare_partner_data(partner_type="customer")
        shipping = customer_data.get("shippingAddress")
        self.assertEqual(shipping["line1"], "300 Warehouse Ave")
        self.assertEqual(shipping["city"], "Warehouse City")

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_sync_bank_account_to_billcom_create(self, mock_request):
        """Test creating a new bank account in Bill.com"""
        # Create a bank account for the vendor
        bank = self.env["res.partner.bank"].create(
            {
                "partner_id": self.vendor_billcom.id,
                "acc_number": "987654321",
                "aba_routing": "123456789",
                "billcom_account_type": "CHECKING",
                "billcom_owner_type": "BUSINESS",
            }
        )

        # Mock API response for creation
        mock_request.return_value = {"id": "bank_new_001", "status": "VERIFIED"}

        # Trigger sync
        bank.sync_bank_account_to_billcom()

        # Verify API call
        mock_request.assert_called_once()
        args, kwargs = mock_request.call_args
        self.assertEqual(kwargs["method"], "POST")
        self.assertIn("bank-account", args[0])
        self.assertEqual(kwargs["data"]["accountNumber"], "987654321")

        # Verify Odoo record updated
        self.assertEqual(bank.billcom_vendor_bank_id, "bank_new_001")
        self.assertEqual(bank.billcom_account_status, "VERIFIED")

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_sync_bank_account_to_billcom_update(self, mock_request):
        """Test updating an existing bank account in Bill.com"""
        # Create a bank account that is already synced
        bank = self.env["res.partner.bank"].create(
            {
                "partner_id": self.vendor_billcom.id,
                "acc_number": "987654321",
                "aba_routing": "123456789",
                "billcom_vendor_bank_id": "bank_existing_001",
            }
        )

        # Mock API response for update
        mock_request.return_value = {"id": "bank_existing_001", "status": "VERIFIED"}

        # Trigger sync
        bank.sync_bank_account_to_billcom()

        # Verify API call uses PATCH and includes ID in URL
        mock_request.assert_called_once()
        args, kwargs = mock_request.call_args
        self.assertEqual(kwargs["method"], "PATCH")
        self.assertIn("bank_existing_001", args[0])

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_sync_bank_account_error_bdc_1233(self, mock_request):
        """Test handling of BDC_1233 error (already setup for epayment)"""
        bank = self.env["res.partner.bank"].create(
            {
                "partner_id": self.vendor_billcom.id,
                "acc_number": "987654321",
                "aba_routing": "123456789",
            }
        )

        # Mock API error
        mock_request.side_effect = UserError(
            "BDC_1233: Vendor already setup for epayment"
        )

        # Verify specific user error is raised
        with self.assertRaises(UserError) as cm:
            bank.sync_bank_account_to_billcom()

        self.assertIn(
            "Vendor already has payment information configured", str(cm.exception)
        )

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_action_fetch_payment_purposes(self, mock_request):
        """Test fetching payment purposes for international vendor"""
        # Setup international vendor
        eur = self.env["res.currency"].search([("name", "=", "EUR")], limit=1)
        if not eur:
            eur = self.env["res.currency"].create({"name": "EUR", "symbol": "€"})

        intl_vendor = self.env["res.partner"].create(
            {
                "name": "Intl Vendor",
                "is_sync_to_billcom": True,
                "country_id": self.env.ref("base.fr").id,
                "billcom_res_currency_id": eur.id,
            }
        )

        # Mock API response
        mock_request.return_value = {
            "results": [
                {"id": "purpose_1", "name": "SERVICES", "description": "Services"},
                {"id": "purpose_2", "name": "GOODS", "description": "Goods"},
            ]
        }

        # Trigger action
        action = intl_vendor.action_fetch_payment_purposes()

        # Verify notification returned
        self.assertEqual(action["tag"], "display_notification")
        self.assertIn("2 payment purpose(s) loaded", action["params"]["message"])

        # Verify purposes created
        purposes = self.env["billcom.payment.purpose"].search([])
        self.assertTrue(len(purposes) >= 2)

    def test_prepare_partner_data_international_bank(self):
        """Test preparing partner data with international bank info"""
        # Setup international vendor with bank
        eur = self.env["res.currency"].search([("name", "=", "EUR")], limit=1)
        if not eur:
            eur = self.env["res.currency"].create({"name": "EUR", "symbol": "€"})

        intl_vendor = self.env["res.partner"].create(
            {
                "name": "Intl Vendor Bank Test",
                "is_sync_to_billcom": True,
                "country_id": self.env.ref("base.fr").id,
                "billcom_res_currency_id": eur.id,
            }
        )

        self.env["res.partner.bank"].create(
            {
                "partner_id": intl_vendor.id,
                "acc_number": "FR76123456789",
                "currency_id": eur.id,
                "bank_id": self.env["res.bank"]
                .create(
                    {
                        "name": "Bank of France",
                        "bic": "BOFFRPP",
                        "country": self.env.ref("base.fr").id,
                    }
                )
                .id,
            }
        )

        # Prepare data
        data = intl_vendor._prepare_partner_data(partner_type="vendor")

        # Verify international bank fields
        payment_info = data["paymentInformation"]
        self.assertEqual(payment_info["bankCountry"], "FR")
        self.assertEqual(payment_info["paymentCurrency"], "EUR")
        self.assertEqual(payment_info["bankInfo"]["swiftBIC"], "BOFFRPP")
        self.assertEqual(payment_info["bankInfo"]["countryISO"], "FR")
