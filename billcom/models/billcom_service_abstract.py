# Copyright 2025 Binhex - Simple Solutions
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
from datetime import timedelta

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class BillcomServiceAbstract(models.AbstractModel):
    _name = "billcom.service.abstract"
    _description = "Bill.com Integration Service Abstract"

    @api.model
    def _get_config(self):
        """Get active BillCom configuration and validate it"""
        config = (
            self.env["billcom.config"]
            .sudo()
            .search(
                [("active", "=", True), ("company_id", "=", self.env.company.id)],
                limit=1,
            )
        )
        if not config:
            raise UserError(
                _("No active BillCom configuration found for company %s")
                % self.env.company.name
            )
        if not config.api_url or not config.username or not config.password:
            raise UserError(_("BillCom API configuration is incomplete"))
        return config

    @api.model
    def _get_token(self):
        """Get authentication token from Bill.com API v3"""
        config = self.env["billcom.config"].search(
            [("active", "=", True), ("company_id", "=", self.env.company.id)], limit=1
        )

        if not config:
            raise UserError(
                _("No active Bill.com configuration found for company %s")
                % self.env.company.name
            )

        if not config.username or not config.password:
            raise UserError(_("API Key and Secret must be configured"))

        # If token exists and is still valid, return it
        if (
            config.token
            and config.token_expiry
            and config.token_expiry > fields.Datetime.now()
        ):
            _logger.debug(
                "Using existing valid token (expires: %s)", config.token_expiry
            )
            return config.token

        _logger.info("Token missing or expired - requesting new token from Bill.com")

        try:
            # Determine authentication endpoint based on environment
            auth_url = f"{config.api_url}/v3/login"

            _logger.info(
                "Authenticating with Bill.com API v3 (%s environment) at: %s",
                config.environment,
                auth_url,
            )

            # Set authentication data based on environment
            payload = {
                "organizationId": config.organization_id,
                "devKey": config.dev_key,
                "username": config.username,
                "password": config.password,
            }

            # Include trusted device ID for MFA-free authentication if configured
            if config.mfa_device_id:
                payload["deviceId"] = config.mfa_device_id
                _logger.info(
                    "Authenticating with trusted device ID for MFA-free session"
                )

            headers = {"accept": "application/json", "content-type": "application/json"}

            # Make authentication request using JSON
            response = requests.post(
                auth_url, json=payload, headers=headers, timeout=40
            )

            # Add debug logging to see the exact request and response
            _logger.debug("Request URL: %s", auth_url)
            _logger.debug("Request data: %s", payload)
            _logger.debug("Response status: %s", response.status_code)
            _logger.debug("Response content: %s", response.content)

            # Check for HTTP errors
            response.raise_for_status()

            # Parse response
            result = response.json()

            # Check for API errors
            if result.get("status") == "error":
                error_message = result.get("errorMessage", "Unknown error")
                _logger.error("Bill.com API authentication error: %s", error_message)
                raise UserError(
                    _("Bill.com API authentication error: %s") % error_message
                )

            # Handle MFA challenge
            if result.get("mfaRequired") and not result.get("sessionId"):
                if config.mfa_device_id:
                    # Device ID was provided but not trusted
                    _logger.error(
                        "MFA Device ID '%s' is not trusted or has expired",
                        config.mfa_device_id,
                    )
                    raise UserError(
                        _(
                            "MFA Device ID is not trusted or has expired.\n\n"
                            "Please:\n"
                            "1. Login to Bill.com web interface\n"
                            "2. Complete MFA and mark 'Trust this device'\n"
                            "3. Update the Device ID in this configuration\n\n"
                            "Or contact Bill.com support to obtain a trusted device ID."
                        )
                    )
                else:
                    # No device ID configured
                    _logger.error(
                        "MFA required but no Device ID configured for payment creation"
                    )
                    raise UserError(
                        _(
                            "MFA-trusted session required for payment creation.\n\n"
                            "Bill.com requires MFA authentication for creating payments.\n\n"
                            "To enable automatic payments:\n"
                            "1. Obtain a trusted Device ID from Bill.com\n"
                            "2. Configure it in the 'MFA Device ID' field\n\n"
                            "See documentation: MFA_PAYMENT_ISSUE.md"
                        )
                    )

            # Successful authentication
            if not result.get("sessionId"):
                raise UserError(_("No session ID received from Bill.com API"))

            result.get("sessionId")

            _logger.info(
                "Successfully authenticated with Bill.com API v3 (%s environment)",
                config.environment,
            )

            # Note: MFA step-up is NOT performed here automatically
            # It will only be performed when needed (e.g., creating payments)
            # See _get_mfa_token() for MFA-specific token retrieval

            # Store the token in the config
            token_expiry = fields.Datetime.now() + timedelta(hours=1)
            config.sudo().write(
                {
                    "token": result.get("sessionId"),
                    "token_expiry": token_expiry,
                    "state": "connected",
                    "last_connection_test": fields.Datetime.now(),
                    "last_error_message": False,
                }
            )

            return result.get("sessionId")

        except requests.exceptions.RequestException as e:
            error_detail = str(e)
            response_content = getattr(e.response, "content", b"").decode(
                "utf-8", errors="ignore"
            )
            status_code = getattr(e.response, "status_code", "Unknown")

            _logger.error(
                "Bill.com Authentication HTTP Error\n"
                "Organization ID: %s\n"
                "API URL: %s\n"
                "Status Code: %s\n"
                "Error: %s\n"
                "Response: %s",
                config.organization_id,
                config.api_url,
                status_code,
                error_detail,
                response_content[:500] if response_content else "No content",
            )

            config.sudo().write(
                {
                    "state": "error",
                    "last_connection_test": fields.Datetime.now(),
                    "last_error_message": f"HTTP {status_code}: {error_detail}",
                }
            )

            raise UserError(
                _("Bill.com authentication failed (HTTP %(status)s): %(detail)s")
                % {"status": status_code, "detail": error_detail}
            ) from e
        except Exception as e:
            error_detail = str(e)
            _logger.error(
                "Bill.com Authentication Unexpected Error\n"
                "Organization ID: %s\n"
                "API URL: %s\n"
                "Error Type: %s\n"
                "Error: %s",
                config.organization_id,
                config.api_url,
                type(e).__name__,
                error_detail,
            )

            config.sudo().write(
                {
                    "state": "error",
                    "last_connection_test": fields.Datetime.now(),
                    "last_error_message": str(e),
                }
            )

            raise UserError(
                _("Unexpected error during Bill.com authentication: %s") % str(e)
            ) from e

    @api.model
    def _get_mfa_token(self):
        """Get MFA-trusted token for payment operations

        This method obtains an MFA-trusted session by logging in with rememberMeId.
        According to Bill.com docs, when you sign in with POST /v3/login including
        rememberMeId and device, you get an MFA-trusted session directly.

        ONLY call this for operations requiring MFA (e.g., POST /v3/payments)

        Returns:
            str: MFA-trusted session ID

        Raises:
            UserError: If MFA configuration is missing
        """
        config = self._get_config()

        # Check if we have rememberMeId configured
        if not config.mfa_remember_me_id:
            _logger.error(
                "Bill.com MFA Configuration Required\n"
                "Payment creation requires MFA-trusted session\n"
                "Organization: %s\n"
                "Action Required: Configure MFA using 'Setup MFA' button\n"
                "Documentation: claudedocs/MFA_QUICK_GUIDE.md",
                config.organization_id,
            )
            raise UserError(
                _(
                    "MFA authentication is required for payment creation.\n\n"
                    "Please use 'Setup MFA' button to configure MFA.\n\n"
                    "See documentation: claudedocs/MFA_QUICK_GUIDE.md"
                )
            )

        # Perform MFA-trusted login with rememberMeId
        _logger.info("Payment operation requested - performing MFA-trusted login")

        try:
            auth_url = f"{config.api_url}/v3/login"

            # Login with rememberMeId and device for MFA-trusted session
            payload = {
                "organizationId": config.organization_id,
                "devKey": config.dev_key,
                "username": config.username,
                "password": config.password,
                "rememberMeId": config.mfa_remember_me_id,
                "device": config.mfa_device_name or "Odoo Integration",
            }

            headers = {"accept": "application/json", "content-type": "application/json"}

            _logger.info("Authenticating with Remember Me ID for MFA-trusted session")

            response = requests.post(
                auth_url, json=payload, headers=headers, timeout=40
            )
            response.raise_for_status()

            result = response.json()
            session_id = result.get("sessionId")

            if not session_id:
                raise UserError(_("No session ID received from MFA login"))

            _logger.info("✅ MFA-trusted session obtained successfully")
            return session_id

        except requests.exceptions.RequestException as e:
            _logger.error("MFA-trusted login failed: %s", str(e))

            # Check if Remember Me ID expired
            error_msg = str(e).lower()
            if "remember" in error_msg and (
                "expired" in error_msg or "invalid" in error_msg
            ):
                config.sudo().write({"mfa_remember_me_id": False})
                _logger.warning("RememberMeId confirmed expired - cleared from config")
                raise UserError(
                    _(
                        "MFA Remember Me ID has expired or is invalid.\n\n"
                        "Please use 'Setup MFA' button to obtain a new one.\n\n"
                        "Remember Me ID is valid for 30 days."
                    )
                ) from e
            else:
                raise UserError(_("MFA-trusted login failed: %s") % str(e)) from e

    @api.model
    def _make_request(
        self,
        endpoint,
        method="GET",
        data=None,
        params=None,
        extra_headers=None,
        is_file_upload=False,
    ):
        """Make a request to Bill.com API v3 with retry logic

        Args:
            endpoint: API endpoint path
            method: HTTP method (GET, POST, PUT, DELETE)
            data: Request body data (dict for JSON, bytes for file upload)
            params: Query parameters
            extra_headers: Additional headers to include
            is_file_upload: True if uploading a file (data should be bytes)
        """
        config = self._get_config()
        max_retries, retry_delay = self._get_retry_config(config)

        for retry_count in range(max_retries + 1):
            try:
                if is_file_upload:
                    return self._execute_request_with_upload(
                        endpoint,
                        method,
                        data,
                        params,
                        config,
                        retry_count,
                        max_retries,
                        extra_headers,
                        is_file_upload,
                    )
                else:
                    return self._execute_request(
                        endpoint,
                        method,
                        data,
                        params,
                        config,
                        retry_count,
                        max_retries,
                        extra_headers,
                    )
            except Exception as e:
                if not self._should_retry(e, retry_count, max_retries):
                    raise
                self._handle_retry_delay(retry_delay, retry_count, max_retries, str(e))

    def _get_retry_config(self, config):
        """Get retry configuration from config"""
        max_retries = getattr(config, "api_max_retries", 3)
        retry_delay = getattr(config, "api_retry_delay", 5)
        return max_retries, retry_delay

    def _execute_request(
        self,
        endpoint,
        method,
        data,
        params,
        config,
        retry_count,
        max_retries,
        extra_headers=None,
    ):
        """Execute a single API request attempt"""
        # Determine if this is a payment creation operation requiring MFA
        is_payment_creation = method == "POST" and endpoint.rstrip("/") == "payments"

        # Get appropriate token based on operation type
        if is_payment_creation:
            _logger.info("Payment creation detected - using MFA-trusted token")
            token = self._get_mfa_token()
        else:
            # Regular operations use regular token (no MFA)
            token = self._get_token()

        url = self._build_api_url(config, endpoint)
        headers = self._build_headers(token, config)

        # Add extra headers if provided
        if extra_headers:
            headers.update(extra_headers)

        self._log_request(method, url, retry_count, max_retries, data, params, headers)

        response = self._send_http_request(method, url, headers, data, params)

        self._log_response(response)

        # Check for expired/invalid session - refresh token and retry once
        # BDC_1109 (401): Session is invalid - need to re-login
        # BDC_1361 (403): Session expired or untrusted
        if response.status_code in (401, 403):
            error_details = self._extract_error_details(response)

            if isinstance(error_details, list):
                for error in error_details:
                    if isinstance(error, dict):
                        error_code = error.get("code")
                        error_message = error.get("message", "")

                        # Handle BDC_1109: Session is invalid (needs re-login)
                        # Handle BDC_1361: Session expired (unless it's "untrusted")
                        should_refresh_token = False

                        if error_code == "BDC_1109":
                            _logger.warning(
                                "Session invalid (BDC_1109) - invalidating token "
                                "and re-authenticating"
                            )
                            should_refresh_token = True

                        elif error_code == "BDC_1361":
                            if "untrusted" in error_message.lower():
                                _logger.error(
                                    "MFA-trusted session required "
                                    "(BDC_1361: Untrusted session). This endpoint "
                                    "requires MFA authentication."
                                )
                                _logger.error(
                                    "Payment creation requires MFA setup."
                                    " Please configure MFA for this Bill.com account."
                                )
                                # Don't retry - this won't be fixed by token refresh
                                break
                            else:
                                _logger.warning(
                                    "Session expired (BDC_1361) - "
                                    "invalidating token and refreshing"
                                )
                                should_refresh_token = True

                        # If we need to refresh the token, do it now
                        if should_refresh_token:
                            try:
                                config.sudo().write(
                                    {
                                        "token": False,
                                        "token_expiry": False,
                                    }
                                )

                                # Use test_connection to get a fresh token
                                config.test_connection()
                                _logger.info(
                                    "Token refreshed successfully, retrying request"
                                )

                                if is_payment_creation:
                                    new_token = self._get_mfa_token()
                                else:
                                    new_token = config.token
                                headers = self._build_headers(new_token, config)

                                # Add extra headers if provided
                                if extra_headers:
                                    headers.update(extra_headers)

                                response = self._send_http_request(
                                    method, url, headers, data, params
                                )
                                self._log_response(response)

                                # Return the result of the retried request
                                return self._process_response(
                                    response, retry_count, max_retries
                                )

                            except Exception as e:
                                _logger.error("Failed to refresh token: %s", str(e))
                                # Fall through to process the original error
                            break

        return self._process_response(response, retry_count, max_retries)

    def _build_api_url(self, config, endpoint):
        """Build the complete API URL

        Webhooks use a different base URL: connect-events instead of connect
        """
        # Check if this is a webhook endpoint
        if endpoint.startswith("webhook:"):
            # Remove the webhook: prefix and use connect-events base
            actual_endpoint = endpoint.replace("webhook:", "")
            base_url = config.api_url.replace("/connect", "/connect-events")
            return f"{base_url.rstrip('/')}/v3/{actual_endpoint.lstrip('/')}"

        # Standard API endpoint
        return f"{config.api_url.rstrip('/')}/v3/{endpoint.lstrip('/')}"

    def _build_headers(self, token, config):
        """Build request headers"""
        return {
            "accept": "application/json",
            "content-type": "application/json",
            "sessionId": token,
            "devKey": config.dev_key,
        }

    def _log_request(
        self, method, url, retry_count, max_retries, data, params, headers
    ):
        """Log request details"""
        _logger.info(
            "Making %s request to Bill.com API (attempt %s/%s): %s",
            method,
            retry_count + 1,
            max_retries + 1,
            url,
        )
        _logger.debug("Request headers: %s", headers)
        _logger.debug("Request data: %s", data)
        _logger.debug("Request params: %s", params)

    def _send_http_request(self, method, url, headers, data, params):
        """Send the actual HTTP request"""
        method_upper = method.upper()

        if method_upper == "GET":
            return requests.get(url, headers=headers, params=params, timeout=30)
        elif method_upper in ["POST", "PUT", "PATCH"]:
            request_method = getattr(requests, method.lower())
            return request_method(url, json=data, headers=headers, timeout=30)
        elif method_upper == "DELETE":
            return requests.delete(url, headers=headers, timeout=30)
        else:
            raise UserError(_("Unsupported HTTP method: %s") % method)

    def _log_response(self, response):
        """Log response details"""
        _logger.info("Bill.com API response status: %s", response.status_code)
        _logger.debug("Bill.com API response content: %s", response.content)

    def _process_response(self, response, retry_count, max_retries):
        """Process and validate the API response"""
        # Check for retryable HTTP status codes
        if self._is_retryable_status(response.status_code):
            raise self._create_retryable_exception(response)

        # Check for HTTP errors (4xx, 5xx)
        if not response.ok:
            # Try to extract detailed error information from response body
            error_details = self._extract_error_details(response)

            # Build descriptive error message
            http_status_map = {
                400: "Bad Request - Invalid data sent to Bill.com API",
                401: "Unauthorized - Authentication failed or session expired",
                403: "Forbidden - Insufficient permissions or session invalid",
                404: "Not Found - Requested resource does not exist",
                422: "Unprocessable Entity - Business logic validation failed",
                423: "Organization Locked - Account temporarily locked by Bill.com",
                429: "Rate Limit Exceeded - Too many API requests",
                500: "Internal Server Error - Bill.com API experiencing issues",
                502: "Bad Gateway - Bill.com API temporarily unavailable",
                503: "Service Unavailable - Bill.com API maintenance or overload",
            }

            status_description = http_status_map.get(
                response.status_code, f"HTTP {response.status_code} Error"
            )

            # Log detailed error information
            _logger.error(
                "Bill.com API Error: %s\n"
                "Request: %s %s\n"
                "Status Code: %s\n"
                "Error Details: %s",
                status_description,
                response.request.method,
                response.url,
                response.status_code,
                error_details,
            )

            # Raise with detailed error message
            response.raise_for_status()

        # Handle empty response
        if not response.content or not response.content.strip():
            return {}

        # Parse JSON response
        try:
            result = response.json()
        except ValueError as e:
            _logger.error(
                "Bill.com API Response Parsing Error\n"
                "Failed to parse JSON response from Bill.com\n"
                "URL: %s\n"
                "Response Length: %s bytes\n"
                "Error: %s\n"
                "Response Preview: %s",
                response.url,
                len(response.content),
                str(e),
                response.content[:500],
            )
            raise self._create_retryable_exception(
                response, f"JSON parsing error: {e}"
            ) from e

        # Check for API-level errors
        if isinstance(result, dict) and result.get("status") == "error":
            error_message = result.get("errorMessage", "Unknown API error")
            error_code = result.get("errorCode", "UNKNOWN")
            _logger.error(
                "Bill.com API-level Error\n"
                "Error Code: %s\n"
                "Error Message: %s\n"
                "URL: %s\n"
                "Full Response: %s",
                error_code,
                error_message,
                response.url,
                result,
            )
            raise self._create_retryable_exception(
                response, f"{error_code}: {error_message}"
            )

        return result

    def _extract_error_details(self, response):
        """Extract detailed error information from response body"""
        try:
            # Try to parse JSON error response
            error_data = response.json()

            # Bill.com API v3 error format
            if isinstance(error_data, list):
                # Array of error objects
                errors = []
                for error in error_data:
                    if isinstance(error, dict):
                        error_info = {
                            "timestamp": error.get("timestamp"),
                            "code": error.get("code"),
                            "severity": error.get("severity"),
                            "category": error.get("category"),
                            "message": error.get("message"),
                            "params": error.get("params", {}),
                        }
                        errors.append(error_info)
                return errors
            elif isinstance(error_data, dict):
                # Single error object or nested errors
                if "errors" in error_data:
                    return error_data["errors"]
                return error_data
            else:
                return error_data
        except Exception as e:
            # If JSON parsing fails, return raw content
            _logger.debug("Could not parse error response as JSON: %s", str(e))
            return response.text

    def _extract_friendly_error(self, exception):  # noqa: C901
        """Extract user-friendly error message from exception

        Args:
            exception: The exception object (usually HTTPError)

        Returns:
            str: User-friendly error message in English
        """
        try:
            # Check if it's an HTTP error with a response
            if hasattr(exception, "response") and exception.response is not None:
                response = exception.response
                error_details = self._extract_error_details(response)

                # Bill.com API v3 format: list of error objects
                if isinstance(error_details, list):
                    messages = []
                    for error in error_details:
                        if isinstance(error, dict) and error.get("message"):
                            msg = error["message"]
                            error_code = error.get("code")

                            # Handle specific error codes
                            if error_code == "BDC_1107":
                                # Organization locked out
                                messages.append(
                                    "⚠️ Organization is temporarily locked by Bill.com.\n"
                                    "This usually happens due to:\n"
                                    "  • Too many API requests in a short time\n"
                                    "  • Multiple failed authentication attempts\n"
                                    "  • Security restrictions on staging environment\n\n"
                                    "Please wait 5-15 minutes and try again.\n"
                                    "If the problem persists, contact Bill.com support."
                                )
                            elif error_code == "BDC_1171":
                                # Duplicate invoice/bill number
                                messages.append(msg)
                            elif ":" in msg:
                                # Make field names more readable
                                # Example: "email: must not be blank" -> "Email is required"
                                field, requirement = msg.split(":", 1)
                                field = field.strip().replace("_", " ").title()
                                requirement = requirement.strip()

                                if "must not be blank" in requirement:
                                    messages.append(f"{field} is required")
                                elif "must not be null" in requirement:
                                    messages.append(f"{field} is required")
                                else:
                                    messages.append(f"{field}: {requirement}")
                            else:
                                messages.append(msg)

                    if messages:
                        return "\n".join(f"• {msg}" for msg in messages)

                # Dict format
                elif isinstance(error_details, dict):
                    if "errorMessage" in error_details:
                        return error_details["errorMessage"]
                    elif "message" in error_details:
                        return error_details["message"]

                # String format
                elif isinstance(error_details, str):
                    return error_details

            # Fallback to exception message
            return str(exception)

        except Exception as e:
            _logger.debug("Could not extract friendly error message: %s", str(e))
            return str(exception)

    def _is_retryable_status(self, status_code):
        """Check if HTTP status code is retryable"""
        return status_code in (429, 500, 502, 503, 504)

    def _create_retryable_exception(self, response, message=None):
        """Create an exception that can be retried"""
        if message is None:
            message = f"HTTP {response.status_code}"

        class RetryableException(Exception):
            def __init__(self, msg, status_code=None):
                super().__init__(msg)
                self.status_code = status_code

        return RetryableException(message, getattr(response, "status_code", None))

    def _should_retry(self, exception, retry_count, max_retries):
        """Determine if an exception should trigger a retry"""
        if retry_count >= max_retries:
            return False

        if hasattr(exception, "response") and exception.response is not None:
            status_code = exception.response.status_code
            if 400 <= status_code < 500:
                _logger.info(
                    "Not retrying request - HTTP %s is a client error that"
                    " won't be fixed by retrying",
                    status_code,
                )
                return False

        # Retry on network errors
        if isinstance(
            exception,
            (
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
                requests.exceptions.RequestException,
            ),
        ):
            return True

        # Retry on our custom retryable exceptions (429, 500, 502, 503, 504)
        if hasattr(exception, "status_code") and self._is_retryable_status(
            exception.status_code
        ):
            return True

        # Retry on JSON parsing errors
        if "JSON parsing error" in str(exception):
            return True

        return False

    def _handle_retry_delay(self, retry_delay, retry_count, max_retries, error_msg):
        """Handle the delay between retries"""
        _logger.warning(
            "Retrying in %s seconds (attempt %s/%s): %s",
            retry_delay,
            retry_count + 1,
            max_retries + 1,
            error_msg,
        )
        import time

        time.sleep(retry_delay)

    @api.model
    def _handle_mfa_challenge(self, mfa_challenge_data, config):
        """Handle MFA challenge from Bill.com API"""
        if not config.enable_mfa:
            raise UserError(_("MFA is required but not configured in settings"))

        # This would typically involve user interaction or stored MFA device
        # For now, we'll log the challenge and raise an error for manual handling
        _logger.warning(
            "MFA challenge received. Challenge data: %s", mfa_challenge_data
        )

        # In a production implementation, this would:
        # 1. Send MFA code to user's device
        # 2. Wait for user input or automated device response
        # 3. Submit MFA response back to Bill.com

        raise UserError(
            _(
                "MFA authentication required. Please check your MFA device "
                "and configure the MFA response in Bill.com settings."
            )
        )

    @api.model
    def _send_mfa_response(self, mfa_token, mfa_code, config):
        """Send MFA response to Bill.com API"""
        try:
            mfa_url = f"{config.api_url}/v3/mfa/verify"

            mfa_data = {
                "mfaToken": mfa_token,
                "mfaCode": mfa_code,
                "deviceId": config.mfa_device_id,
            }

            headers = {
                "accept": "application/json",
                "content-type": "application/json",
                "devKey": config.dev_key,
            }

            response = requests.post(
                mfa_url, json=mfa_data, headers=headers, timeout=30
            )
            response.raise_for_status()

            result = response.json()

            if result.get("status") == "error":
                error_message = result.get("errorMessage", "MFA verification failed")
                raise UserError(_("MFA verification error: %s") % error_message)

            return result.get("sessionId")

        except requests.exceptions.RequestException as e:
            _logger.error("MFA verification request failed: %s", str(e))
            raise UserError(_("MFA verification request failed: %s") % str(e)) from e

    def _get_state_id(self, state_code):
        """Get state ID from state code"""
        if not state_code:
            return False
        state = self.env["res.country.state"].search(
            [("code", "=", state_code)], limit=1
        )
        return state.id if state else False

    def _get_country_id(self, country_code):
        """Get country ID from country code"""
        if not country_code:
            return False
        country = self.env["res.country"].search([("code", "=", country_code)], limit=1)
        return country.id if country else False

    @api.model
    def _mfa_step_up(self, config, session_id):
        """Convert current session to MFA-trusted using step-up

        Args:
            config: billcom.config record
            session_id: Current session ID to upgrade

        Returns:
            bool: True if step-up successful

        Raises:
            UserError: If step-up fails
        """
        try:
            # Step 1: Check current MFA status
            status_url = f"{config.api_url}/v3/login/session"
            status_headers = {
                "accept": "application/json",
                "content-type": "application/json",
                "sessionId": session_id,
                "devKey": config.dev_key,
            }

            _logger.info("Checking MFA status at: %s", status_url)
            status_response = requests.get(
                status_url, headers=status_headers, timeout=30
            )

            if status_response.status_code != 200:
                _logger.error("Failed to retrieve MFA status: %s", status_response.text)
                raise UserError(
                    _("Failed to check MFA status: %s") % status_response.text
                )

            status_result = status_response.json()
            mfa_status = status_result.get("mfaStatus")
            _logger.info("Current MFA status: %s", mfa_status)

            # Step 2: If already MFA complete, no need for step-up
            if mfa_status == "COMPLETE":
                _logger.info(
                    "✅ Session already has MFA COMPLETE status - no step-up needed"
                )
                return True

            # Step 3: Perform MFA step-up
            _logger.info("MFA status is '%s' - performing step-up", mfa_status)
            step_up_url = f"{config.api_url}/v3/mfa/step-up"

            headers = {
                "accept": "application/json",
                "content-type": "application/json",
                "sessionId": session_id,
                "devKey": config.dev_key,
            }

            payload = {
                "rememberMeId": config.mfa_remember_me_id,
                "device": config.mfa_device_name or "Odoo Integration",
            }

            _logger.info("Step-up URL: %s", step_up_url)
            _logger.info(
                "Step-up payload: %s",
                {
                    "rememberMeId": config.mfa_remember_me_id[:20] + "...",
                    "device": payload["device"],
                },
            )

            response = requests.post(
                step_up_url, json=payload, headers=headers, timeout=30
            )

            _logger.info("Step-up response status: %s", response.status_code)
            _logger.info("Step-up response body: %s", response.text)

            response.raise_for_status()

            result = response.json()

            # Step 4: Verify MFA status after step-up
            # Instead of trusting only the "trusted" field, check actual MFA status
            _logger.info("Verifying MFA status after step-up...")
            verify_response = requests.get(
                status_url, headers=status_headers, timeout=30
            )

            if verify_response.status_code == 200:
                verify_result = verify_response.json()
                new_mfa_status = verify_result.get("mfaStatus")
                _logger.info("MFA status after step-up: %s", new_mfa_status)

                if new_mfa_status == "COMPLETE":
                    _logger.info(
                        "✅ Session successfully marked as MFA-trusted via step-up"
                    )
                    return True
                else:
                    _logger.warning(
                        "Step-up completed but MFA status is still '%s' (expected 'COMPLETE')",
                        new_mfa_status,
                    )
                    # Don't clear Remember Me ID yet, might be a timing issue
                    raise UserError(
                        _(
                            "MFA step-up completed but session is not yet trusted.\n\n"
                            "Status: %s\n\n"
                            "Please try again in a moment.\n\n"
                            "If the problem persists, use 'Setup MFA' button"
                            " to reconfigure."
                        )
                        % new_mfa_status
                    )
            else:
                # Verification failed but step-up succeeded
                # Accept the step-up result
                if result.get("trusted"):
                    _logger.info(
                        "✅ Step-up response indicates trusted "
                        "(verification failed but accepting)"
                    )
                    return True
                else:
                    _logger.error(
                        "Step-up response did not indicate trusted status: %s", result
                    )
                    # Only clear Remember Me ID if we're sure it's invalid
                    # Don't clear on first failure - might be temporary issue
                    raise UserError(
                        _(
                            "MFA step-up did not establish trusted session.\n\n"
                            "Response: %s\n\n"
                            "Please try again. If the problem persists, use 'Setup MFA' button."
                        )
                        % result
                    )

        except requests.exceptions.RequestException as e:
            _logger.error("MFA step-up request failed: %s", str(e))

            # Check if it's definitely an expired/invalid Remember Me ID
            error_msg = str(e).lower()

            # Only clear Remember Me ID if error explicitly mentions it's expired/invalid
            if "remember" in error_msg and (
                "expired" in error_msg or "invalid" in error_msg
            ):
                config.sudo().write({"mfa_remember_me_id": False})
                _logger.warning(
                    "RememberMeId confirmed expired or invalid - cleared from config"
                )
                raise UserError(
                    _(
                        "MFA Remember Me ID has expired or is invalid.\n\n"
                        "Please use 'Setup MFA' button to obtain a new one.\n\n"
                        "Remember Me ID is valid for 30 days."
                    )
                ) from e
            else:
                # Other network/API error - don't clear Remember Me ID
                _logger.warning(
                    "MFA step-up failed but Remember Me ID kept (may be temporary issue)"
                )
                raise UserError(
                    _(
                        "MFA step-up request failed.\n\n"
                        "Error: %s\n\n"
                        "Please try again. If the problem persists, check:\n"
                        "1. Network connectivity\n"
                        "2. Bill.com API status\n"
                        "3. Use 'Setup MFA' button to reconfigure if needed"
                    )
                    % str(e)
                ) from e

    def _execute_request_with_upload(  # noqa: C901
        self,
        endpoint,
        method,
        data,
        params,
        config,
        retry_count,
        max_retries,
        extra_headers=None,
        is_file_upload=False,
    ):
        """Execute request with support for file uploads"""
        # Determine if this is a payment creation operation requiring MFA
        is_payment_creation = method == "POST" and endpoint.rstrip("/") == "payments"

        # Get appropriate token based on operation type
        if is_payment_creation:
            _logger.info("Payment creation detected - using MFA-trusted token")
            token = self._get_mfa_token()
        else:
            token = self._get_token()

        url = self._build_api_url(config, endpoint)
        headers = self._build_headers(token, config)

        # Modify headers for file upload
        if is_file_upload:
            headers["content-type"] = "application/octet-stream"

        # Add extra headers if provided
        if extra_headers:
            headers.update(extra_headers)

        self._log_request(method, url, retry_count, max_retries, data, params, headers)

        # Send request with file upload support
        if is_file_upload:
            response = self._send_file_upload_request(
                method, url, headers, data, params
            )
        else:
            response = self._send_http_request(method, url, headers, data, params)

        self._log_response(response)

        # Check for expired/invalid session
        if response.status_code in (401, 403):
            error_details = self._extract_error_details(response)

            if isinstance(error_details, list):
                for error in error_details:
                    if isinstance(error, dict):
                        error_code = error.get("code")
                        error_message = error.get("message", "")

                        should_refresh_token = False

                        if error_code == "BDC_1109":
                            _logger.warning(
                                "Session invalid (BDC_1109) - invalidating token"
                                " and re-authenticating"
                            )
                            should_refresh_token = True

                        elif error_code == "BDC_1361":
                            if "untrusted" in error_message.lower():
                                _logger.error(
                                    "MFA-trusted session required "
                                    "(BDC_1361: Untrusted session)"
                                )
                                break
                            else:
                                _logger.warning(
                                    "Session expired (BDC_1361) - invalidating"
                                    " token and refreshing"
                                )
                                should_refresh_token = True

                        if should_refresh_token:
                            try:
                                config.sudo().write(
                                    {
                                        "token": False,
                                        "token_expiry": False,
                                    }
                                )
                                config.test_connection()
                                _logger.info(
                                    "Token refreshed successfully, retrying request"
                                )

                                if is_payment_creation:
                                    new_token = self._get_mfa_token()
                                else:
                                    new_token = config.token
                                headers = self._build_headers(new_token, config)

                                if is_file_upload:
                                    headers["content-type"] = "application/octet-stream"

                                if extra_headers:
                                    headers.update(extra_headers)

                                if is_file_upload:
                                    response = self._send_file_upload_request(
                                        method, url, headers, data, params
                                    )
                                else:
                                    response = self._send_http_request(
                                        method, url, headers, data, params
                                    )
                                self._log_response(response)

                                return self._process_response(
                                    response, retry_count, max_retries
                                )

                            except Exception as e:
                                _logger.error("Failed to refresh token: %s", str(e))
                            break

        return self._process_response(response, retry_count, max_retries)

    def _send_file_upload_request(self, method, url, headers, file_data, params):
        """Send HTTP request with file data"""
        method_upper = method.upper()

        if method_upper == "POST":
            return requests.post(
                url, data=file_data, headers=headers, params=params, timeout=60
            )
        elif method_upper == "PUT":
            return requests.put(
                url, data=file_data, headers=headers, params=params, timeout=60
            )
        else:
            raise UserError(_("File upload only supports POST and PUT methods"))

    @api.model
    def _download_document(self, download_url):
        """Download document from Bill.com

        Args:
            download_url: Download URL from Bill.com document response

        Returns:
            bytes: File content
        """
        config = self._get_config()
        token = self._get_token()

        headers = {
            "sessionId": token,
            "devKey": config.dev_key,
        }

        _logger.info("Downloading document from Bill.com: %s", download_url)

        try:
            response = requests.get(download_url, headers=headers, timeout=60)
            response.raise_for_status()

            _logger.info(
                "Document downloaded successfully (%d bytes)", len(response.content)
            )
            return response.content

        except requests.exceptions.HTTPError as e:
            error_details = self._extract_error_details(e.response)

            http_status_map = {
                401: "Unauthorized - Authentication failed or session expired",
                403: "Forbidden - Insufficient permissions",
                404: "Not Found - Document no longer exists",
            }

            status_description = http_status_map.get(
                e.response.status_code, f"HTTP {e.response.status_code}"
            )

            _logger.error(
                "Bill.com Document Download Error: %s\n"
                "URL: %s\n"
                "Status Code: %s\n"
                "Error Details: %s",
                status_description,
                download_url,
                e.response.status_code,
                error_details,
            )
            raise

        except requests.exceptions.RequestException as e:
            _logger.error("Document download failed: %s", str(e))
            raise

    @api.model
    def get_invoice_payment_link(self, invoice_id, customer_id, customer_email):
        """Get payment link for a customer invoice

        Args:
            invoice_id (str): Bill.com invoice ID
            customer_id (str): Bill.com customer ID
            customer_email (str): Customer email address for payment receipt

        Returns:
            str: Payment link URL from Bill.com

        Raises:
            UserError: If API request fails or response is invalid
        """
        if not invoice_id:
            raise UserError(_("Invoice ID is required to get payment link"))
        if not customer_id:
            raise UserError(_("Customer ID is required to get payment link"))
        if not customer_email:
            raise UserError(_("Customer email is required to get payment link"))

        _logger.info(
            "Requesting payment link for invoice %s (customer: %s)",
            invoice_id,
            customer_id,
        )

        try:
            data = {
                "customerId": customer_id,
                "email": customer_email,
            }

            response = self._make_request(
                f"invoices/{invoice_id}/payment-link", method="POST", data=data
            )

            if not response or not response.get("paymentLink"):
                error_msg = _(
                    "Failed to get payment link from Bill.com. Response: %s"
                ) % str(response)
                _logger.error(error_msg)
                raise UserError(error_msg)

            payment_link = response.get("paymentLink")
            _logger.info(
                "Successfully retrieved payment link for invoice %s", invoice_id
            )
            return payment_link

        except Exception as e:
            friendly_message = self._extract_friendly_error(e)
            _logger.error(
                "Error getting payment link for invoice %s: %s", invoice_id, str(e)
            )
            raise UserError(
                _("Failed to get payment link from Bill.com:\n\n%s") % friendly_message
            ) from e

    @api.model
    def send_invoice_email(self, invoice_id, recipient_emails=None):
        """Send invoice payment reminder email via Bill.com

        Args:
            invoice_id (str): Bill.com invoice ID
            recipient_emails (list): List of recipient email addresses
                                    If not provided, Bill.com uses default customer email

        Returns:
            dict: API response from Bill.com

        Raises:
            UserError: If API request fails
        """
        if not invoice_id:
            raise UserError(_("Invoice ID is required to send email"))

        _logger.info("Sending invoice payment reminder for invoice %s", invoice_id)

        try:
            data = {}

            # Add recipient emails if provided
            if recipient_emails:
                if not isinstance(recipient_emails, list):
                    recipient_emails = [recipient_emails]
                data["recipient"] = {"to": recipient_emails}
                _logger.info(
                    "Sending to custom recipients: %s", ", ".join(recipient_emails)
                )
            else:
                _logger.info("Using Bill.com default customer email")

            response = self._make_request(
                f"invoices/{invoice_id}/email", method="POST", data=data
            )

            _logger.info(
                "Successfully sent payment reminder for invoice %s", invoice_id
            )
            return response

        except Exception as e:
            friendly_message = self._extract_friendly_error(e)
            _logger.error(
                "Error sending payment reminder for invoice %s: %s", invoice_id, str(e)
            )
            raise UserError(
                _("Failed to send payment reminder via Bill.com:\n\n%s")
                % friendly_message
            ) from e
