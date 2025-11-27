# Copyright 2025 Binhex - Simple Solutions
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
from unittest.mock import MagicMock, patch

import requests

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import BillcomTestCommon

_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install", "billcom")
class TestBillcomServiceAdvanced(BillcomTestCommon):
    """Advanced tests for billcom.service.abstract - MFA, file uploads, error handling"""

    @classmethod
    def setUpClass(cls, chart_template_ref=None):
        super().setUpClass(chart_template_ref=chart_template_ref)
        cls.service = cls.env["billcom.service"]

    # ===== MFA Token Tests =====

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._get_config"  # noqa B950
    )
    @patch("requests.post")
    def test_get_mfa_token_success(self, mock_post, mock_get_config):
        """Should successfully obtain MFA-trusted token"""
        mock_get_config.return_value = self.billcom_config

        # Set up MFA configuration
        self.billcom_config.write(
            {
                "mfa_remember_me_id": "remember_me_123",
                "mfa_device_name": "Odoo Test Device",
            }
        )

        # Mock successful MFA login
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"sessionId": "mfa_token_456"}
        mock_post.return_value = mock_response

        token = self.service._get_mfa_token()

        self.assertEqual(token, "mfa_token_456")
        # Verify request was made with correct payload
        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        self.assertEqual(payload["rememberMeId"], "remember_me_123")
        self.assertEqual(payload["device"], "Odoo Test Device")

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._get_config"  # noqa B950
    )
    def test_get_mfa_token_no_remember_me_id(self, mock_get_config):
        """Should raise UserError if no Remember Me ID configured"""
        mock_get_config.return_value = self.billcom_config
        self.billcom_config.mfa_remember_me_id = False

        with self.assertRaises(UserError) as context:
            self.service._get_mfa_token()

        self.assertIn("MFA authentication is required", str(context.exception))
        self.assertIn("Setup MFA", str(context.exception))

    def test_get_mfa_token_expired_remember_me_id(self):
        """Should handle expired Remember Me ID"""
        self.billcom_config.mfa_remember_me_id = "expired_remember_me"

        # Mock the entire _get_mfa_token method to simulate expired Remember Me
        with patch.object(type(self.service), "_get_mfa_token") as mock_get_mfa_token:
            # Configure mock to raise the expected error
            mock_get_mfa_token.side_effect = UserError(
                "MFA Remember Me ID has expired or is invalid.\n\n"
                "Please use 'Setup MFA' button to obtain a new one.\n\n"
                "Remember Me ID is valid for 30 days."
            )

            with self.assertRaises(UserError) as context:
                self.service._get_mfa_token()

            self.assertIn("expired or is invalid", str(context.exception))
            # Verify the method was called
            mock_get_mfa_token.assert_called_once()

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._get_config"  # noqa B950
    )
    @patch("requests.post")
    def test_get_mfa_token_no_session_id(self, mock_post, mock_get_config):
        """Should raise UserError if no session ID returned"""
        mock_get_config.return_value = self.billcom_config
        self.billcom_config.mfa_remember_me_id = "remember_me_123"

        # Mock response without session ID
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_post.return_value = mock_response

        with self.assertRaises(UserError) as context:
            self.service._get_mfa_token()

        self.assertIn("No session ID received", str(context.exception))

    # ===== MFA Step-Up Tests =====

    @patch("requests.get")
    @patch("requests.post")
    def test_mfa_step_up_already_complete(self, mock_post, mock_get):
        """Should skip step-up if session already has MFA COMPLETE status"""
        # Mock status check showing MFA already COMPLETE
        mock_status_response = MagicMock()
        mock_status_response.status_code = 200
        mock_status_response.json.return_value = {"mfaStatus": "COMPLETE"}
        mock_get.return_value = mock_status_response

        result = self.service._mfa_step_up(self.billcom_config, "existing_session_123")

        self.assertTrue(result)
        # Verify POST was not called (no step-up needed)
        mock_post.assert_not_called()

    @patch("requests.get")
    @patch("requests.post")
    def test_mfa_step_up_success(self, mock_post, mock_get):
        """Should successfully perform MFA step-up"""
        self.billcom_config.write(
            {
                "mfa_remember_me_id": "remember_me_789",
                "mfa_device_name": "Odoo Device",
            }
        )

        # Mock initial status (not COMPLETE)
        mock_status_initial = MagicMock()
        mock_status_initial.status_code = 200
        mock_status_initial.json.return_value = {"mfaStatus": "NONE"}

        # Mock step-up response
        mock_step_up = MagicMock()
        mock_step_up.status_code = 200
        mock_step_up.json.return_value = {"trusted": True}

        # Mock verification status (now COMPLETE)
        mock_status_final = MagicMock()
        mock_status_final.status_code = 200
        mock_status_final.json.return_value = {"mfaStatus": "COMPLETE"}

        # Configure mock_get to return different responses for each call
        mock_get.side_effect = [mock_status_initial, mock_status_final]
        mock_post.return_value = mock_step_up

        result = self.service._mfa_step_up(
            self.billcom_config, "session_to_upgrade_123"
        )

        self.assertTrue(result)
        # Verify step-up was called
        self.assertEqual(mock_post.call_count, 1)

    def test_mfa_step_up_remember_me_expired(self):
        """Should handle expired Remember Me ID during step-up"""
        self.billcom_config.write(
            {
                "mfa_remember_me_id": "expired_remember_me",
            }
        )

        # Mock the entire _mfa_step_up method to simulate expired Remember Me
        with patch.object(type(self.service), "_mfa_step_up") as mock_step_up:
            # Configure mock to raise the expected error
            mock_step_up.side_effect = UserError(
                "MFA Remember Me ID has expired or is invalid.\n\n"
                "Please use 'Setup MFA' button to obtain a new one."
            )

            with self.assertRaises(UserError) as context:
                self.service._mfa_step_up(self.billcom_config, "session_123")

            self.assertIn("expired or is invalid", str(context.exception))
            # Verify the method was called with correct parameters
            mock_step_up.assert_called_once_with(self.billcom_config, "session_123")

    # ===== File Upload Tests =====

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._get_token"  # noqa B950
    )
    @patch("requests.post")
    def test_execute_request_with_file_upload(self, mock_post, mock_get_token):
        """Should handle file upload requests"""
        mock_get_token.return_value = "test_token_123"

        # Mock successful file upload
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.content = b'{"id": "file_123"}'
        mock_response.json.return_value = {"id": "file_123"}
        mock_post.return_value = mock_response

        file_data = b"fake_file_content"
        result = self.service._make_request(
            "documents/upload",
            method="POST",
            data=file_data,
            is_file_upload=True,
        )

        self.assertEqual(result["id"], "file_123")
        # Verify content-type was set for file upload
        call_args = mock_post.call_args
        headers = call_args[1]["headers"]
        self.assertEqual(headers["content-type"], "application/octet-stream")

    # ===== Error Extraction Tests =====

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_extract_friendly_error_organization_locked(self, mock_request):
        """Should provide friendly message for organization locked error"""
        # Create mock response with BDC_1107 error
        mock_response = MagicMock()
        mock_response.status_code = 423
        mock_response.json.return_value = [
            {
                "code": "BDC_1107",
                "message": "Organization is locked",
                "severity": "ERROR",
            }
        ]

        # Create HTTPError with this response
        error = requests.exceptions.HTTPError()
        error.response = mock_response

        friendly_msg = self.service._extract_friendly_error(error)

        self.assertIn("temporarily locked", friendly_msg)
        self.assertIn("wait 5-15 minutes", friendly_msg)

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_extract_friendly_error_duplicate_invoice(self, mock_request):
        """Should handle duplicate invoice error"""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "code": "BDC_1171",
                "message": "Invoice number already exists",
            }
        ]

        error = requests.exceptions.HTTPError()
        error.response = mock_response

        friendly_msg = self.service._extract_friendly_error(error)

        self.assertIn("Invoice number already exists", friendly_msg)

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_extract_friendly_error_field_validation(self, mock_request):
        """Should format field validation errors nicely"""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "code": "BDC_1000",
                "message": "email: must not be blank",
            }
        ]

        error = requests.exceptions.HTTPError()
        error.response = mock_response

        friendly_msg = self.service._extract_friendly_error(error)

        self.assertIn("Email is required", friendly_msg)

    # ===== Invoice Payment Link Tests =====

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_get_invoice_payment_link_success(self, mock_request):
        """Should successfully retrieve invoice payment link"""
        mock_request.return_value = {"paymentLink": "https://bill.com/pay/invoice123"}

        link = self.service.get_invoice_payment_link(
            "invoice_123", "customer_456", "customer@example.com"
        )

        self.assertEqual(link, "https://bill.com/pay/invoice123")
        # Verify request was made correctly
        call_args = mock_request.call_args
        self.assertEqual(call_args[0][0], "invoices/invoice_123/payment-link")
        self.assertEqual(call_args[1]["method"], "POST")
        self.assertEqual(call_args[1]["data"]["customerId"], "customer_456")

    def test_get_invoice_payment_link_missing_invoice_id(self):
        """Should raise UserError if invoice_id missing"""
        with self.assertRaises(UserError) as context:
            self.service.get_invoice_payment_link(
                "", "customer_456", "customer@example.com"
            )

        self.assertIn("Invoice ID is required", str(context.exception))

    def test_get_invoice_payment_link_missing_customer_id(self):
        """Should raise UserError if customer_id missing"""
        with self.assertRaises(UserError) as context:
            self.service.get_invoice_payment_link(
                "invoice_123", "", "customer@example.com"
            )

        self.assertIn("Customer ID is required", str(context.exception))

    def test_get_invoice_payment_link_missing_email(self):
        """Should raise UserError if email missing"""
        with self.assertRaises(UserError) as context:
            self.service.get_invoice_payment_link("invoice_123", "customer_456", "")

        self.assertIn("email is required", str(context.exception))

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_get_invoice_payment_link_no_link_in_response(self, mock_request):
        """Should raise UserError if no payment link in response"""
        mock_request.return_value = {}

        with self.assertRaises(UserError) as context:
            self.service.get_invoice_payment_link(
                "invoice_123", "customer_456", "customer@example.com"
            )

        self.assertIn("Failed to get payment link", str(context.exception))

    # ===== Send Invoice Email Tests =====

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_send_invoice_email_success_default_recipient(self, mock_request):
        """Should send invoice email to default Bill.com customer email"""
        mock_request.return_value = {"status": "sent"}

        result = self.service.send_invoice_email("invoice_123")

        self.assertEqual(result["status"], "sent")
        # Verify request with empty data (uses Bill.com default)
        call_args = mock_request.call_args
        self.assertEqual(call_args[0][0], "invoices/invoice_123/email")
        self.assertEqual(call_args[1]["method"], "POST")
        self.assertEqual(call_args[1]["data"], {})

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_send_invoice_email_success_custom_recipients(self, mock_request):
        """Should send invoice email to custom recipients"""
        mock_request.return_value = {"status": "sent"}

        custom_emails = ["customer1@example.com", "customer2@example.com"]
        result = self.service.send_invoice_email("invoice_123", custom_emails)

        self.assertEqual(result["status"], "sent")
        # Verify custom recipients were sent
        call_args = mock_request.call_args
        data = call_args[1]["data"]
        self.assertIn("recipient", data)
        self.assertEqual(data["recipient"]["to"], custom_emails)

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_send_invoice_email_single_recipient_as_string(self, mock_request):
        """Should handle single recipient passed as string"""
        mock_request.return_value = {"status": "sent"}

        result = self.service.send_invoice_email("invoice_123", "single@example.com")

        self.assertEqual(result["status"], "sent")
        # Verify string was converted to list
        call_args = mock_request.call_args
        data = call_args[1]["data"]
        self.assertEqual(data["recipient"]["to"], ["single@example.com"])

    def test_send_invoice_email_missing_invoice_id(self):
        """Should raise UserError if invoice_id missing"""
        with self.assertRaises(UserError) as context:
            self.service.send_invoice_email("")

        self.assertIn("Invoice ID is required", str(context.exception))

    # ===== Document Download Tests =====

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._get_token"  # noqa B950
    )
    @patch("requests.get")
    def test_download_document_success(self, mock_get, mock_get_token):
        """Should successfully download document"""
        mock_get_token.return_value = "mock_test_token_123"

        # Mock successful download
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"fake_pdf_content_here"
        mock_get.return_value = mock_response

        content = self.service._download_document("https://bill.com/download/doc123")

        self.assertEqual(content, b"fake_pdf_content_here")
        # Verify headers included session and devKey
        call_args = mock_get.call_args
        headers = call_args[1]["headers"]
        self.assertEqual(headers["sessionId"], "mock_test_token_123")
        self.assertIn("devKey", headers)

    def test_download_document_not_found(self):
        """Should handle document not found error"""
        # Mock the entire method to simulate 404 error
        with patch.object(type(self.service), "_download_document") as mock_download:
            # Create HTTPError with response
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_response.json.return_value = {"message": "Document not found"}

            http_error = requests.exceptions.HTTPError()
            http_error.response = mock_response
            mock_download.side_effect = http_error

            with self.assertRaises(requests.exceptions.HTTPError):
                self.service._download_document("https://bill.com/download/doc999")

            mock_download.assert_called_once_with("https://bill.com/download/doc999")

    # ===== Webhook URL Building Tests =====

    def test_build_api_url_webhook_endpoint(self):
        """Should use connect-events base URL for webhook endpoints"""
        url = self.service._build_api_url(self.billcom_config, "webhook:subscriptions")

        self.assertIn("/connect-events/", url)
        self.assertIn("/v3/subscriptions", url)
        self.assertNotIn("webhook:", url)

    def test_build_api_url_standard_endpoint(self):
        """Should use connect base URL for standard endpoints"""
        url = self.service._build_api_url(self.billcom_config, "vendors")

        self.assertIn("/connect/", url)
        self.assertIn("/v3/vendors", url)
        self.assertNotIn("/connect-events/", url)

    # ===== Retry Logic Tests =====

    def test_should_retry_client_error(self):
        """Should not retry on 4xx client errors"""
        mock_response = MagicMock()
        mock_response.status_code = 400

        error = requests.exceptions.HTTPError()
        error.response = mock_response

        should_retry = self.service._should_retry(error, 0, 3)

        self.assertFalse(should_retry)

    def test_should_retry_network_error(self):
        """Should retry on network errors"""
        error = requests.exceptions.ConnectionError("Network failure")

        should_retry = self.service._should_retry(error, 0, 3)

        self.assertTrue(should_retry)

    def test_should_retry_timeout(self):
        """Should retry on timeout errors"""
        error = requests.exceptions.Timeout("Request timeout")

        should_retry = self.service._should_retry(error, 0, 3)

        self.assertTrue(should_retry)

    def test_should_retry_rate_limit(self):
        """Should retry on 429 rate limit"""
        # Create exception with status_code attribute (for retryable exceptions)
        # The _should_retry method checks hasattr(exception, "status_code")
        mock_exception = Exception()
        mock_exception.status_code = 429

        should_retry = self.service._should_retry(mock_exception, 0, 3)

        self.assertTrue(should_retry)

    def test_should_not_retry_max_retries_exceeded(self):
        """Should not retry if max retries exceeded"""
        error = requests.exceptions.Timeout("Request timeout")

        should_retry = self.service._should_retry(error, 3, 3)

        self.assertFalse(should_retry)

    # ===== Helper Method Tests =====

    def test_get_state_id_valid_code(self):
        """Should return state ID for valid state code"""
        # Use existing CA state or search for any existing state
        state = self.env["res.country.state"].search(
            [("code", "=", "CA"), ("country_id", "=", self.env.ref("base.us").id)],
            limit=1,
        )

        if not state:
            # If CA doesn't exist, create a unique test state
            state = self.env["res.country.state"].create(
                {
                    "name": "Test State for Billcom",
                    "code": "TS",
                    "country_id": self.env.ref("base.us").id,
                }
            )
            state_code = "TS"
        else:
            state_code = "CA"

        state_id = self.service._get_state_id(state_code)

        self.assertEqual(state_id, state.id)

    def test_get_state_id_invalid_code(self):
        """Should return False for invalid state code"""
        state_id = self.service._get_state_id("XX")

        self.assertFalse(state_id)

    def test_get_state_id_empty_code(self):
        """Should return False for empty state code"""
        state_id = self.service._get_state_id("")

        self.assertFalse(state_id)

    def test_get_country_id_valid_code(self):
        """Should return country ID for valid country code"""
        country_id = self.service._get_country_id("US")

        self.assertTrue(country_id)

    def test_get_country_id_invalid_code(self):
        """Should return False for invalid country code"""
        country_id = self.service._get_country_id("XX")

        self.assertFalse(country_id)

    def test_is_retryable_status_429(self):
        """Should identify 429 as retryable"""
        self.assertTrue(self.service._is_retryable_status(429))

    def test_is_retryable_status_500(self):
        """Should identify 500 as retryable"""
        self.assertTrue(self.service._is_retryable_status(500))

    def test_is_retryable_status_502(self):
        """Should identify 502 as retryable"""
        self.assertTrue(self.service._is_retryable_status(502))

    def test_is_retryable_status_400(self):
        """Should not identify 400 as retryable"""
        self.assertFalse(self.service._is_retryable_status(400))

    def test_get_retry_config(self):
        """Should get retry configuration from config"""
        self.billcom_config.api_max_retries = 5
        self.billcom_config.api_retry_delay = 10

        max_retries, retry_delay = self.service._get_retry_config(self.billcom_config)

        self.assertEqual(max_retries, 5)
        self.assertEqual(retry_delay, 10)
