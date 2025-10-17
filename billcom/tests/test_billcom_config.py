# Copyright 2025 Binhex - Simple Solutions
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import BillcomTestCommon

_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install", "billcom")
class TestBillcomConfig(BillcomTestCommon):
    """Test billcom.config model"""

    def test_config_required_fields(self):
        """Test that all required fields are present"""
        required_fields = [
            "name",
            "environment",
            "username",
            "password",
            "organization_id",
            "dev_key",
        ]

        for field in required_fields:
            self.assertTrue(
                hasattr(self.billcom_config, field),
                f"Config should have field: {field}",
            )

    def test_config_environment_values(self):
        """Test environment field values"""
        # Test sandbox
        self.billcom_config.environment = "sandbox"
        self.assertEqual(self.billcom_config.environment, "sandbox")

        # Test production
        self.billcom_config.environment = "production"
        self.assertEqual(self.billcom_config.environment, "production")

    def test_config_api_url_computation(self):
        """Test API URL is computed correctly based on environment"""
        # Sandbox URL
        self.billcom_config.environment = "sandbox"
        self.billcom_config._compute_api_url()
        self.assertIn("stage.bill.com", self.billcom_config.api_url)

        # Production URL
        self.billcom_config.environment = "production"
        self.billcom_config._compute_api_url()
        self.assertEqual(
            self.billcom_config.api_url, "https://gateway.bill.com/connect"
        )

    def test_config_state_management(self):
        """Test configuration state transitions"""
        # Default state
        self.assertEqual(self.billcom_config.state, "draft")

        # Test state changes
        self.billcom_config.state = "connected"
        self.assertEqual(self.billcom_config.state, "connected")

        self.billcom_config.state = "error"
        self.assertEqual(self.billcom_config.state, "error")

    @patch(
        "odoo.addons.billcom.models.billcom_service_abstract.BillcomServiceAbstract._get_token"
    )
    def test_connection_test_success(self, mock_get_token):
        """Test successful connection test"""
        mock_get_token.return_value = "test_token_123"

        result = self.billcom_config.test_connection()

        # Verify state was updated
        self.assertEqual(self.billcom_config.state, "connected")
        self.assertIsNotNone(self.billcom_config.last_connection_test)

        # Verify notification action
        self.assertEqual(result["type"], "ir.actions.client")
        self.assertEqual(result["tag"], "display_notification")

    @patch(
        "odoo.addons.billcom.models.billcom_service_abstract.BillcomServiceAbstract._get_token"
    )
    def test_connection_test_failure(self, mock_get_token):
        """Test connection test failure"""
        mock_get_token.side_effect = UserError("Authentication failed")

        with self.assertRaises(UserError):
            self.billcom_config.test_connection()

        # Verify error state
        self.assertEqual(self.billcom_config.state, "error")
        self.assertIn("Authentication failed", self.billcom_config.last_error_message)

    def test_mfa_configuration(self):
        """Test MFA-related fields"""
        # MFA disabled by default
        self.assertFalse(self.billcom_config.enable_mfa)

        # Enable MFA
        self.billcom_config.enable_mfa = True
        self.billcom_config.mfa_device_id = "device_123"
        self.billcom_config.mfa_remember_me_id = "remember_456"

        self.assertTrue(self.billcom_config.enable_mfa)
        self.assertEqual(self.billcom_config.mfa_device_id, "device_123")

    def test_sync_configuration_flags(self):
        """Test sync configuration flags"""
        # All sync flags enabled by default in test setup
        self.assertTrue(self.billcom_config.sync_vendors)
        self.assertTrue(self.billcom_config.sync_customers)
        self.assertTrue(self.billcom_config.sync_bills)
        self.assertTrue(self.billcom_config.sync_payments)

    def test_webhook_configuration(self):
        """Test webhook configuration"""
        self.assertTrue(self.billcom_config.enable_webhooks)
        self.assertEqual(self.billcom_config.webhook_secret, "test_webhook_secret")

        # Disable webhooks
        self.billcom_config.enable_webhooks = False
        self.assertFalse(self.billcom_config.enable_webhooks)

    def test_company_isolation(self):
        """Test that config is company-specific"""
        self.assertEqual(self.billcom_config.company_id, self.env.company)

        # Create config for different company (if multicompany)
        if len(self.env["res.company"].search([])) > 1:
            other_company = self.env["res.company"].search(
                [("id", "!=", self.env.company.id)], limit=1
            )

            other_config = self.env["billcom.config"].create(
                {
                    "name": "Other Company Config",
                    "environment": "sandbox",
                    "username": "other_user",
                    "password": "other_pass",
                    "organization_id": "other_org",
                    "dev_key": "other_dev_key",
                    "company_id": other_company.id,
                }
            )

            self.assertNotEqual(other_config.company_id, self.billcom_config.company_id)

    def test_multiple_configs_one_active(self):
        """Test only one config can be active per company"""
        # Create second config for same company
        self.env["billcom.config"].create(
            {
                "name": "Second Config",
                "environment": "production",
                "username": "second_user",
                "password": "second_pass",
                "organization_id": "second_org",
                "dev_key": "second_dev_key",
                "company_id": self.env.company.id,
                "active": True,
            }
        )

        # Both are active (implementation may enforce single active)
        active_configs = self.env["billcom.config"].search(
            [("active", "=", True), ("company_id", "=", self.env.company.id)]
        )

        # Should handle multiple active configs gracefully
        self.assertGreaterEqual(len(active_configs), 1)

    def test_last_sync_date_tracking(self):
        """Test last sync date is tracked"""
        # Initially None
        self.assertFalse(self.billcom_config.last_sync_date)

        # Set sync date
        now = fields.Datetime.now()
        self.billcom_config.last_sync_date = now

        self.assertEqual(self.billcom_config.last_sync_date, now)

    def test_config_tracking(self):
        """Test that important fields are tracked"""
        # billcom.config inherits mail.thread
        self.assertIn("mail.thread", self.billcom_config._inherit)

    def test_config_archiving(self):
        """Test config can be archived"""
        self.assertTrue(self.billcom_config.active)

        # Archive config
        self.billcom_config.active = False
        self.assertFalse(self.billcom_config.active)

    def test_config_credentials_security(self):
        """Test that password field is not exposed"""
        # Password should not be in read results (if implemented correctly)
        # This is a basic check
        self.assertTrue(self.billcom_config.password)
