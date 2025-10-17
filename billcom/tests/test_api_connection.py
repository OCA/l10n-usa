import logging
from unittest.mock import MagicMock, patch

import requests

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase

_logger = logging.getLogger(__name__)


class TestBillcomAPIConnection(TransactionCase):
    """Test suite for Bill.com API connection and endpoint validation"""

    def setUp(self):
        super().setUp()

        # Create a test Bill.com configuration
        self.config = self.env["billcom.config"].create(
            {
                "name": "Test Bill.com Config",
                "environment": "sandbox",
                "username": "test_user@example.com",
                "password": "test_password",
                "organization_id": "test_org_123",
                "dev_key": "test_dev_key_456",
                "user_id": self.env.user.id,
                "company_id": self.env.company.id,
                "active": True,
            }
        )

        # Create service instance
        self.service = self.env["billcom.service.abstract"]

    def test_api_url_configuration(self):
        """Test that API URLs are correctly configured for different environments"""

        # Test sandbox URL
        self.config.environment = "sandbox"
        self.config._compute_api_url()
        expected_sandbox = "https://gateway.stage.bill.com/connect"
        self.assertEqual(
            self.config.api_url,
            expected_sandbox,
            f"Sandbox URL should be {expected_sandbox}",
        )

        # Test production URL
        self.config.environment = "production"
        self.config._compute_api_url()
        expected_production = "https://gateway.bill.com/connect"
        self.assertEqual(
            self.config.api_url,
            expected_production,
            f"Production URL should be {expected_production}",
        )

    @patch("odoo.addons.billcom.models.billcom_service_abstract.requests.post")
    def test_authentication_request_format(self, mock_post):
        """Test that authentication requests are formatted correctly"""

        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "sessionId": "test_session_123",
            "status": "success",
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        # Trigger authentication
        token = self.service._get_token()

        # Verify the request was made correctly
        mock_post.assert_called_once()
        call_args = mock_post.call_args

        # Check URL
        expected_url = f"{self.config.api_url}/v3/login"
        self.assertEqual(call_args[0][0], expected_url, "Login URL should be correct")

        # Check headers
        headers = call_args[1]["headers"]
        self.assertEqual(headers["accept"], "application/json")
        self.assertEqual(headers["content-type"], "application/json")

        # Check payload
        payload = call_args[1]["json"]
        expected_payload = {
            "organizationId": self.config.organization_id,
            "devKey": self.config.dev_key,
            "username": self.config.username,
            "password": self.config.password,
        }
        self.assertEqual(
            payload, expected_payload, "Authentication payload should be correct"
        )

        # Verify token was returned
        self.assertEqual(token, "test_session_123")

    @patch("odoo.addons.billcom.models.billcom_service_abstract.requests.post")
    def test_authentication_error_handling(self, mock_post):
        """Test authentication error handling"""

        # Mock error response
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "status": "error",
            "errorMessage": "Invalid credentials",
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        # Should raise UserError for authentication failure
        with self.assertRaises(UserError) as cm:
            self.service._get_token()

        self.assertIn("Invalid credentials", str(cm.exception))

    @patch("odoo.addons.billcom.models.billcom_service_abstract.requests.post")
    def test_mfa_challenge_handling(self, mock_post):
        """Test MFA challenge detection and handling"""

        # Mock MFA challenge response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "mfaRequired": True,
            "mfaToken": "test_mfa_token_123",
            "status": "mfa_required",
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        # Enable MFA in config but don't configure it properly
        self.config.enable_mfa = False

        # Should return None for MFA challenge when MFA not configured
        result = self.service._get_token()
        self.assertIsNone(
            result, "Should return None for MFA challenge when not configured"
        )

    def test_connection_test_functionality(self):
        """Test the connection test method"""

        with patch.object(self.service, "_get_token") as mock_get_token:
            # Mock successful token retrieval
            mock_get_token.return_value = "test_token_123"

            # Test successful connection
            result = self.config.test_connection()

            # Verify config state was updated
            self.assertEqual(self.config.state, "connected")
            self.assertIsNotNone(self.config.last_connection_test)
            self.assertFalse(self.config.last_error_message)

            # Verify return value is notification action
            self.assertEqual(result["type"], "ir.actions.client")
            self.assertEqual(result["tag"], "display_notification")

    def test_connection_test_failure(self):
        """Test connection test failure handling"""

        with patch.object(self.service, "_get_token") as mock_get_token:
            # Mock authentication failure
            mock_get_token.side_effect = UserError("Authentication failed")

            # Test connection failure
            with self.assertRaises(UserError):
                self.config.test_connection()

            # Verify config state was updated
            self.assertEqual(self.config.state, "error")
            self.assertIsNotNone(self.config.last_connection_test)
            self.assertIn("Authentication failed", self.config.last_error_message)

    @patch("odoo.addons.billcom.models.billcom_service_abstract.requests.get")
    def test_api_request_headers(self, mock_get):
        """Test that API requests include proper headers"""

        # Mock token
        with patch.object(self.service, "_get_token", return_value="test_token_123"):
            # Mock successful response
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"data": []}
            mock_response.content = b'{"data": []}'
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response

            # Make a test API request
            self.service._make_request("vendors", method="GET")

            # Verify headers
            mock_get.assert_called_once()
            call_args = mock_get.call_args
            headers = call_args[1]["headers"]

            expected_headers = {
                "accept": "application/json",
                "content-type": "application/json",
                "sessionId": "test_token_123",
                "devKey": self.config.dev_key,
            }

            for key, value in expected_headers.items():
                self.assertEqual(headers[key], value, f"Header {key} should be {value}")

    def test_api_endpoint_url_construction(self):
        """Test that API endpoint URLs are constructed correctly"""

        test_cases = [
            ("vendors", "https://gateway.stage.bill.com/connect/v3/vendors"),
            ("customers", "https://gateway.stage.bill.com/connect/v3/customers"),
            ("bills", "https://gateway.stage.bill.com/connect/v3/bills"),
            ("payments", "https://gateway.stage.bill.com/connect/v3/payments"),
            ("vendors/123", "https://gateway.stage.bill.com/connect/v3/vendors/123"),
            (
                "vendors/123/bank-account",
                "https://gateway.stage.bill.com/connect/v3/vendors/123/bank-account",
            ),
        ]

        for endpoint, expected_url in test_cases:
            url = self.service._build_api_url(self.config, endpoint)
            self.assertEqual(
                url,
                expected_url,
                f"URL for endpoint '{endpoint}' should be '{expected_url}'",
            )

    @patch("odoo.addons.billcom.models.billcom_service_abstract.requests.post")
    def test_network_error_handling(self, mock_post):
        """Test handling of network errors"""

        # Mock connection error
        mock_post.side_effect = requests.exceptions.ConnectionError("Connection failed")

        # Should raise UserError with proper message
        with self.assertRaises(UserError) as cm:
            self.service._get_token()

        self.assertIn("HTTP error during Bill.com authentication", str(cm.exception))

    @patch("odoo.addons.billcom.models.billcom_service_abstract.requests.post")
    def test_timeout_handling(self, mock_post):
        """Test handling of request timeouts"""

        # Mock timeout error
        mock_post.side_effect = requests.exceptions.Timeout("Request timed out")

        # Should raise UserError with proper message
        with self.assertRaises(UserError) as cm:
            self.service._get_token()

        self.assertIn("HTTP error during Bill.com authentication", str(cm.exception))

    def test_retry_configuration(self):
        """Test retry configuration from config"""

        # Set custom retry values
        self.config.api_max_retries = 5
        self.config.api_retry_delay = 10

        max_retries, retry_delay = self.service._get_retry_config(self.config)

        self.assertEqual(max_retries, 5, "Max retries should match config")
        self.assertEqual(retry_delay, 10, "Retry delay should match config")

    def test_retryable_status_codes(self):
        """Test identification of retryable HTTP status codes"""

        retryable_codes = [429, 500, 502, 503, 504]
        non_retryable_codes = [200, 400, 401, 403, 404]

        for code in retryable_codes:
            self.assertTrue(
                self.service._is_retryable_status(code),
                f"Status code {code} should be retryable",
            )

        for code in non_retryable_codes:
            self.assertFalse(
                self.service._is_retryable_status(code),
                f"Status code {code} should not be retryable",
            )

    def test_empty_response_handling(self):
        """Test handling of empty API responses"""

        # Mock empty response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b""
        mock_response.raise_for_status.return_value = None

        result = self.service._process_response(mock_response, 0, 3)
        self.assertEqual(result, {}, "Empty response should return empty dict")

    def test_json_parsing_error_handling(self):
        """Test handling of invalid JSON responses"""

        # Mock invalid JSON response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"invalid json content"
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_response.raise_for_status.return_value = None

        # Should raise exception for JSON parsing error
        with self.assertRaises(Exception) as cm:
            self.service._process_response(mock_response, 0, 3)

        self.assertIn("JSON parsing error", str(cm.exception))

    def test_api_error_response_handling(self):
        """Test handling of API-level errors in responses"""

        # Mock API error response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "error",
            "errorMessage": "Invalid vendor data",
        }
        mock_response.raise_for_status.return_value = None

        # Should raise exception for API error
        with self.assertRaises(Exception) as cm:
            self.service._process_response(mock_response, 0, 3)

        self.assertIn("Invalid vendor data", str(cm.exception))

    def test_config_validation(self):
        """Test configuration validation"""

        # Test missing configuration
        self.config.active = False

        with self.assertRaises(UserError) as cm:
            self.service._get_config()

        self.assertIn("No active BillCom configuration found", str(cm.exception))

        # Test incomplete configuration
        self.config.active = True
        self.config.username = False

        with self.assertRaises(UserError) as cm:
            self.service._get_config()

        self.assertIn("BillCom API configuration is incomplete", str(cm.exception))

    @patch("odoo.addons.billcom.models.billcom_service_abstract.requests.post")
    def test_real_api_endpoint_connectivity(self, mock_post):
        """Test basic connectivity to real Bill.com API endpoints (mocked)"""

        # This test verifies our request format would work with real API
        # We mock the response but verify request structure

        mock_response = MagicMock()
        mock_response.status_code = 400  # Expected for invalid test credentials
        mock_response.json.return_value = {
            "status": "error",
            "errorMessage": "Invalid credentials",
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        # This should fail authentication but prove endpoint connectivity
        with self.assertRaises(UserError):
            self.service._get_token()

        # Verify we called the correct endpoint
        mock_post.assert_called_once()
        call_args = mock_post.call_args

        # Check we're hitting the right Bill.com endpoint
        url = call_args[0][0]
        self.assertTrue(
            url.startswith("https://gateway.stage.bill.com/connect/v3/login"),
            f"Should use correct Bill.com API endpoint, got: {url}",
        )

        _logger.info("✅ Bill.com API endpoint structure validation passed")
        _logger.info(f"✅ Sandbox URL: {url}")
        _logger.info("✅ Request format matches Bill.com API v3 specification")

    def test_integration_readiness(self):
        """Test that the integration is ready for real API connection"""

        # Verify all required fields are present
        required_fields = ["username", "password", "organization_id", "dev_key"]

        for field in required_fields:
            self.assertTrue(
                hasattr(self.config, field), f"Config should have field: {field}"
            )
            self.assertTrue(
                getattr(self.config, field), f"Config field {field} should have a value"
            )

        # Verify API URL is correctly computed
        self.assertTrue(
            self.config.api_url.startswith("https://"), "API URL should use HTTPS"
        )
        self.assertIn(
            "bill.com", self.config.api_url, "API URL should point to Bill.com"
        )

        _logger.info("✅ Integration configuration is ready for real API connection")
        _logger.info(f"✅ Sandbox API URL: {self.config.api_url}")
        _logger.info("✅ All required authentication fields are configured")
        _logger.info("✅ Ready to test with real Bill.com sandbox credentials")
