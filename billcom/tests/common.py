from unittest.mock import MagicMock, patch

from odoo import fields

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


class BillcomTestCommon(AccountTestInvoicingCommon):
    """Base test class for Bill.com integration tests"""

    @classmethod
    def setUpClass(cls, chart_template_ref=None):
        super().setUpClass(chart_template_ref=chart_template_ref)

        # ========== GLOBAL MOCKS - Prevent ALL real API connections ==========
        # Mock authentication to prevent real API calls
        cls.patcher_get_token = patch(
            "odoo.addons.billcom.models.billcom_service_abstract.BillcomServiceAbstract._get_token",  # noqa: B950
            return_value="mock_test_token_123",
        )
        cls.patcher_get_token.start()

        # ========== Test Data Setup ==========

        # Create Bill.com configuration
        cls.billcom_config = cls.env["billcom.config"].create(
            {
                "name": "Test Bill.com Config",
                "environment": "sandbox",
                "username": "test_api_key",
                "password": "test_api_secret",
                "user_id": cls.env.user.id,
                "organization_id": "test_org_id",
                "dev_key": "test_dev_key",
                "enable_webhooks": True,
                "webhook_secret": "test_webhook_secret",
                "sync_vendors": True,
                "sync_customers": True,
                "sync_bills": True,
                "sync_payments": True,
                "enable_mfa": False,
                "active": True,
                "company_id": cls.env.company.id,
            }
        )

        # Create test vendor with Bill.com sync enabled
        cls.vendor_billcom = cls.env["res.partner"].create(
            {
                "name": "Test Vendor Bill.com",
                "supplier_rank": 1,
                "customer_rank": 0,
                "is_sync_to_billcom": True,
                "billcom_id": "test_vendor_123",
                "billcom": "test_vendor_123",
                "street": "123 Test Street",
                "city": "Test City",
                "state_id": cls.env.ref("base.state_us_5").id,  # California
                "zip": "12345",
                "country_id": cls.env.ref("base.us").id,
                "email": "vendor@test.com",
                "phone": "+1-555-123-4567",
            }
        )

        # Create test customer with Bill.com sync enabled
        cls.customer_billcom = cls.env["res.partner"].create(
            {
                "name": "Test Customer Bill.com",
                "supplier_rank": 0,
                "customer_rank": 1,
                "is_sync_to_billcom": True,
                "billcom_id": "test_customer_456",
                "billcom": "test_customer_456",
                "street": "456 Customer Ave",
                "city": "Customer City",
                "state_id": cls.env.ref("base.state_us_5").id,  # California
                "zip": "67890",
                "country_id": cls.env.ref("base.us").id,
                "email": "customer@test.com",
                "phone": "+1-555-987-6543",
            }
        )

        # Create test bank journal for payments
        cls.bank_journal = cls.env["account.journal"].create(
            {
                "name": "Test Bank Journal",
                "type": "bank",
                "code": "TBNK",
                "company_id": cls.env.company.id,
            }
        )

        # Create vendor bill for testing
        cls.vendor_bill = cls.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": cls.vendor_billcom.id,
                "invoice_date": fields.Date.today(),
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": cls.product_a.id,
                            "quantity": 1,
                            "price_unit": 100.0,
                            "account_id": cls.company_data[
                                "default_account_expense"
                            ].id,
                        },
                    )
                ],
                "billcom_id": "test_bill_789",
            }
        )

    def _mock_billcom_api_success(self, return_data=None):
        """Mock successful Bill.com API response"""
        if return_data is None:
            return_data = {"id": "test_id_123", "status": "success"}

        mock_response = MagicMock()
        mock_response.json.return_value = return_data
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        return mock_response

    def _mock_billcom_api_error(self, status_code=400, error_message="Test error"):
        """Mock failed Bill.com API response"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "error",
            "errorMessage": error_message,
        }
        mock_response.status_code = status_code
        mock_response.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
        return mock_response

    def _get_mock_vendor_data(self, vendor_id="test_vendor_123"):
        """Get mock vendor data from Bill.com API"""
        return {
            "id": vendor_id,
            "name": "Test Vendor Bill.com",
            "email": "vendor@test.com",
            "phone": "+1-555-123-4567",
            "isActive": True,
            "shortName": "TestVendor",
            "address": {
                "line1": "123 Test Street",
                "line2": "",
                "city": "Test City",
                "stateOrProvince": "CA",
                "zipOrPostalCode": "12345",
                "country": "US",
            },
            "accountType": "BUSINESS",
            "isVendor": True,
        }

    def _get_mock_payment_data(self, payment_id="test_payment_123"):
        """Get mock payment data from Bill.com API"""
        return {
            "id": payment_id,
            "vendorId": "test_vendor_123",
            "amount": 100.0,
            "processDate": fields.Date.today().isoformat(),
            "singleStatus": "SCHEDULED",
            "confirmationNumber": "CONF123",
            "transactionNumber": "TXN456",
            "description": "Test Payment",
        }

    def _get_mock_webhook_data(
        self, event_type="payment.statusChanged", entity_id="test_payment_123"
    ):
        """Get mock webhook data"""
        return {
            "eventType": event_type,
            "entityId": entity_id,
            "timestamp": fields.Datetime.now().isoformat(),
            "organizationId": "test_org_id",
        }

    @classmethod
    def tearDownClass(cls):
        """Cleanup test resources"""
        # Stop all patchers
        cls.patcher_get_token.stop()
        super().tearDownClass()
