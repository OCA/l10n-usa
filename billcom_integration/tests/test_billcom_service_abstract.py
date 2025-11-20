# Copyright 2025 Binhex - Simple Solutions
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
from datetime import timedelta
from unittest.mock import MagicMock, patch

import requests

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import BillcomTestCommon

_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install", "billcom")
class TestBillcomServiceAbstract(BillcomTestCommon):
    """Tests for billcom.service.abstract core methods"""

    @classmethod
    def setUpClass(cls, chart_template_ref=None):
        super().setUpClass(chart_template_ref=chart_template_ref)
        cls.service = cls.env["billcom.service"]

    # ===== Configuration Tests =====

    def test_get_config_success(self):
        """Should return active config for current company"""
        config = self.service._get_config()

        self.assertTrue(config)
        self.assertEqual(config.id, self.billcom_config.id)
        self.assertEqual(config.company_id, self.env.company)

    def test_get_config_no_active_config(self):
        """Should raise UserError if no active config exists"""
        self.billcom_config.active = False

        with self.assertRaises(UserError) as context:
            self.service._get_config()

        self.assertIn("No active BillCom configuration", str(context.exception))

    def test_get_config_incomplete_config(self):
        """Should raise UserError if config is incomplete"""
        # Set api_url to False to make config incomplete
        self.billcom_config.api_url = False

        with self.assertRaises(UserError) as context:
            self.service._get_config()

        self.assertIn("incomplete", str(context.exception))

    # ===== Token Management Tests =====

    def test_get_token_uses_cached_valid_token(self):
        """Should return cached token if still valid"""
        # Set valid token
        self.billcom_config.write(
            {
                "token": "cached_token_123",
                "token_expiry": fields.Datetime.now() + timedelta(hours=1),
            }
        )

        # Stop global patcher to test real behavior
        self.patcher_get_token.stop()
        try:
            token = self.service._get_token()
            self.assertEqual(token, "cached_token_123")
        finally:
            self.patcher_get_token.start()

    def test_get_token_expired_token_requests_new(self):
        """Should request new token if cached token is expired"""
        # Set expired token
        self.billcom_config.write(
            {
                "token": "expired_token",
                "token_expiry": fields.Datetime.now() - timedelta(hours=1),
            }
        )

        # Global patcher will provide new token
        token = self.service._get_token()
        self.assertEqual(token, "mock_test_token_123")

    def test_get_token_no_config(self):
        """Should raise UserError if no active config"""
        self.billcom_config.active = False

        # Stop global patcher to test real error
        self.patcher_get_token.stop()
        try:
            with self.assertRaises(UserError) as context:
                self.service._get_token()

            self.assertIn("No active Bill.com configuration", str(context.exception))
        finally:
            self.patcher_get_token.start()

    def test_get_token_missing_credentials(self):
        """Should raise UserError if username/password missing"""
        # Create a new config without username to test validation
        incomplete_config = self.env["billcom.config"].create(
            {
                "name": "Incomplete Config",
                "environment": "sandbox",
                "username": "",  # Empty username
                "password": "test_pass",
                "organization_id": "test_org",
                "dev_key": "test_dev",
                "user_id": self.env.user.id,
                "company_id": self.env.company.id,
                "active": False,  # Not active, won't interfere
            }
        )

        # Temporarily make this the active config
        self.billcom_config.active = False
        incomplete_config.active = True

        # Stop global patcher to test real error
        self.patcher_get_token.stop()
        try:
            with self.assertRaises(UserError) as context:
                self.service._get_token()

            self.assertIn("API Key and Secret", str(context.exception))
        finally:
            # Restore original config
            incomplete_config.active = False
            self.billcom_config.active = True
            self.patcher_get_token.start()

    # ===== HTTP Request Tests =====

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_make_request_success(self, mock_request):
        """Should make successful API request"""
        mock_request.return_value = {"id": "test_123", "status": "success"}

        result = self.service._make_request("test/endpoint", method="GET")

        self.assertEqual(result["id"], "test_123")
        self.assertEqual(result["status"], "success")

    @patch("requests.get")
    def test_send_http_request_get_success(self, mock_get):
        """Should send GET request successfully"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "test"}
        mock_get.return_value = mock_response

        response = self.service._send_http_request(
            method="GET",
            url="https://api.bill.com/test",
            headers={"Authorization": "Bearer token"},
            data=None,
            params={"key": "value"},
        )

        self.assertEqual(response.status_code, 200)
        mock_get.assert_called_once()

    @patch("requests.post")
    def test_send_http_request_post_success(self, mock_post):
        """Should send POST request successfully"""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": "new_123"}
        mock_post.return_value = mock_response

        response = self.service._send_http_request(
            method="POST",
            url="https://api.bill.com/create",
            headers={"Content-Type": "application/json"},
            data={"name": "Test"},
            params=None,
        )

        self.assertEqual(response.status_code, 201)
        mock_post.assert_called_once()

    @patch("requests.get")
    def test_send_http_request_timeout(self, mock_get):
        """Should handle request timeout"""
        mock_get.side_effect = requests.Timeout("Request timeout")

        with self.assertRaises(requests.Timeout):
            self.service._send_http_request(
                method="GET",
                url="https://api.bill.com/test",
                headers={},
                data=None,
                params=None,
            )

    @patch("requests.get")
    def test_send_http_request_connection_error(self, mock_get):
        """Should handle connection error"""
        mock_get.side_effect = requests.ConnectionError("Connection failed")

        with self.assertRaises(requests.ConnectionError):
            self.service._send_http_request(
                method="GET",
                url="https://api.bill.com/test",
                headers={},
                data=None,
                params=None,
            )

    # ===== Response Processing Tests =====

    def test_process_response_success_200(self):
        """Should process successful 200 response"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True, "data": "test"}

        result = self.service._process_response(
            mock_response, retry_count=0, max_retries=3
        )

        self.assertEqual(result["success"], True)
        self.assertEqual(result["data"], "test")

    def test_process_response_success_201(self):
        """Should process successful 201 created response"""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": "created_123"}

        result = self.service._process_response(
            mock_response, retry_count=0, max_retries=3
        )

        self.assertEqual(result["id"], "created_123")

    def test_is_retryable_status_429(self):
        """Should identify 429 as retryable"""
        self.assertTrue(self.service._is_retryable_status(429))

    def test_is_retryable_status_500(self):
        """Should identify 500 as retryable"""
        self.assertTrue(self.service._is_retryable_status(500))

    def test_is_retryable_status_503(self):
        """Should identify 503 as retryable"""
        self.assertTrue(self.service._is_retryable_status(503))

    def test_is_retryable_status_400_not_retryable(self):
        """Should identify 400 as not retryable"""
        self.assertFalse(self.service._is_retryable_status(400))

    def test_is_retryable_status_404_not_retryable(self):
        """Should identify 404 as not retryable"""
        self.assertFalse(self.service._is_retryable_status(404))

    # ===== URL Building Tests =====

    def test_build_api_url_with_leading_slash(self):
        """Should build API URL correctly with leading slash in endpoint"""
        url = self.service._build_api_url(self.billcom_config, "/vendors")

        self.assertEqual(url, f"{self.billcom_config.api_url}/v3/vendors")

    def test_build_api_url_without_leading_slash(self):
        """Should build API URL correctly without leading slash"""
        url = self.service._build_api_url(self.billcom_config, "vendors")

        self.assertEqual(url, f"{self.billcom_config.api_url}/v3/vendors")

    def test_build_api_url_complex_endpoint(self):
        """Should build API URL for complex endpoint"""
        url = self.service._build_api_url(
            self.billcom_config, "vendors/vendor123/bills"
        )

        self.assertEqual(
            url, f"{self.billcom_config.api_url}/v3/vendors/vendor123/bills"
        )

    # ===== Error Handling Tests =====
    def test_extract_friendly_error_timeout(self):
        """Should extract friendly message from Timeout"""
        error = requests.Timeout("Request timed out")

        friendly_error = self.service._extract_friendly_error(error)

        self.assertIn("timed out", friendly_error.lower())

    # ===== Retry Logic Tests =====
    def test_should_retry_retryable_exception(self):
        """Should retry on retryable exception"""
        # Create a retryable exception
        RetryableException = self.service._create_retryable_exception
        error = RetryableException(MagicMock(status_code=503), "Service unavailable")

        should_retry = self.service._should_retry(error, retry_count=0, max_retries=3)

        self.assertTrue(should_retry)

    def test_should_retry_max_retries_exceeded(self):
        """Should not retry if max retries exceeded"""
        RetryableException = self.service._create_retryable_exception
        error = RetryableException(MagicMock(status_code=503), "Service unavailable")

        should_retry = self.service._should_retry(error, retry_count=3, max_retries=3)

        self.assertFalse(should_retry)

    def test_should_retry_non_retryable_exception(self):
        """Should not retry on non-retryable exception"""
        error = ValueError("Invalid input")

        should_retry = self.service._should_retry(error, retry_count=0, max_retries=3)

        self.assertFalse(should_retry)

    # ===== Helper Method Tests =====

    def test_get_state_id_valid_code(self):
        """Should get state ID from valid code"""
        # US California state
        state_id = self.service._get_state_id("CA")

        self.assertTrue(state_id)
        self.assertIsInstance(state_id, int)

    def test_get_state_id_invalid_code(self):
        """Should return False for invalid state code"""
        state_id = self.service._get_state_id("XX")

        self.assertFalse(state_id)

    def test_get_country_id_valid_code(self):
        """Should get country ID from valid code"""
        country_id = self.service._get_country_id("US")

        self.assertTrue(country_id)
        self.assertIsInstance(country_id, int)

    def test_get_country_id_invalid_code(self):
        """Should return False for invalid country code"""
        country_id = self.service._get_country_id("XX")

        self.assertFalse(country_id)
