import json
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
            return config.token

        try:
            # Determine authentication endpoint based on environment
            auth_url = f"{config.api_url}/login"

            _logger.info(
                "Authenticating with Bill.com API v3 (%s environment) at: %s",
                config.environment,
                auth_url,
            )

            # Set authentication data based on environment
            auth_data = {
                "organizationId": config.organization_id,
                "devKey": config.dev_key,
                "username": config.username,
                "password": config.password,
            }

            headers = {"accept": "application/json", "content-type": "application/json"}

            # Make authentication request using JSON
            response = requests.post(
                auth_url, json=auth_data, headers=headers, timeout=30
            )

            # Add debug logging to see the exact request and response
            _logger.debug("Request URL: %s", auth_url)
            _logger.debug("Request data: %s", auth_data)
            _logger.debug("Response status: %s", response.status_code)
            _logger.debug("Response content: %s", response.content)

            # Check for HTTP errors
            response.raise_for_status()

            # Parse response
            result = response.json()

            # Check for API errors
            if result.get("status") == "error" or not result.get("sessionId"):
                error_message = result.get("errorMessage", "Unknown error")
                _logger.error("Bill.com API authentication error: %s", error_message)
                raise UserError(
                    _("Bill.com API authentication error: %s") % error_message
                )

            _logger.info(
                "Successfully authenticated with Bill.com API v3 (%s environment)",
                config.environment,
            )

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
            _logger.error("HTTP error during Bill.com authentication: %s", str(e))
            _logger.error(
                "Response content: %s", getattr(e.response, "content", "No content")
            )

            config.sudo().write(
                {
                    "state": "error",
                    "last_connection_test": fields.Datetime.now(),
                    "last_error_message": str(e),
                }
            )

            raise UserError(
                _("HTTP error during Bill.com authentication: %s") % str(e)
            ) from e
        except Exception as e:
            _logger.error("Unexpected error during Bill.com authentication: %s", str(e))

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
    def _make_request(self, endpoint, method="GET", data=None, params=None):
        """Make a request to Bill.com API v3 with retry logic"""
        config = self.env["billcom.config"].search(
            [("active", "=", True), ("company_id", "=", self.env.company.id)], limit=1
        )

        if not config:
            raise UserError(
                _("No active Bill.com configuration found for company %s")
                % self.env.company.name
            )

        # Get retry configuration
        max_retries = (
            config.api_max_retries if hasattr(config, "api_max_retries") else 3
        )
        retry_delay = (
            config.api_retry_delay if hasattr(config, "api_retry_delay") else 5
        )

        # Initialize variables for retry logic
        retry_count = 0

        while retry_count <= max_retries:
            try:
                # Get token (fresh token for each retry attempt)
                token = self._get_token()

                # Normalize URL path with proper handling of slashes
                url = f"{config.api_url.rstrip('/')}/{endpoint.lstrip('/')}"

                headers = {
                    "accept": "application/json",
                    "content-type": "application/json",
                    "sessionId": token,
                    "devKey": config.dev_key,
                }

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

                # Make request based on method
                if method.upper() == "GET":
                    response = requests.get(
                        url, headers=headers, params=params, timeout=30
                    )
                elif method.upper() in ["POST", "PUT", "PATCH"]:
                    _logger.info(
                        "%s request to %s with data: %s", method.upper(), url, data
                    )
                    json_str = json.dumps(data)
                    _logger.info("%s request JSON: %s", method.upper(), json_str)
                    request_method = getattr(requests, method.lower())
                    response = request_method(
                        url, json=data, headers=headers, timeout=30
                    )
                elif method.upper() == "DELETE":
                    response = requests.delete(url, headers=headers, timeout=30)
                else:
                    raise UserError(_("Unsupported HTTP method: %s") % method)

                _logger.info("Bill.com API response status: %s", response.status_code)
                _logger.info("Bill.com API response content: %s", response.content)

                # Check for retryable status codes
                if (
                    response.status_code in (429, 500, 502, 503, 504)
                    and retry_count < max_retries
                ):
                    retry_count += 1
                    _logger.warning(
                        "Retryable status code %s received, retrying in %s seconds "
                        "(attempt %s/%s)",
                        response.status_code,
                        retry_delay,
                        retry_count,
                        max_retries + 1,
                    )
                    import time

                    time.sleep(retry_delay)
                    continue

            except requests.exceptions.ConnectionError as e:
                # Network connection errors are good candidates for retry
                if retry_count < max_retries:
                    retry_count += 1
                    _logger.warning(
                        "Connection error, retrying in %s seconds (attempt %s/%s): %s",
                        retry_delay,
                        retry_count,
                        max_retries + 1,
                        str(e),
                    )
                    import time

                    time.sleep(retry_delay)
                    continue
                else:
                    _logger.error(
                        "Bill.com API connection failed after %s attempts: %s",
                        retry_count + 1,
                        str(e),
                    )
                    raise UserError(
                        _("Bill.com API connection failed after %s attempts: %s")
                        % (retry_count + 1, str(e))
                    ) from e

            except requests.exceptions.Timeout as e:
                # Timeout errors are good candidates for retry
                if retry_count < max_retries:
                    retry_count += 1
                    _logger.warning(
                        "Timeout error, retrying in %s seconds (attempt %s/%s): %s",
                        retry_delay,
                        retry_count,
                        max_retries + 1,
                        str(e),
                    )
                    import time

                    time.sleep(retry_delay)
                    continue
                else:
                    _logger.error(
                        "Bill.com API timeout after %s attempts: %s",
                        retry_count + 1,
                        str(e),
                    )
                    raise UserError(
                        _("Bill.com API timeout after %s attempts: %s")
                        % (retry_count + 1, str(e))
                    ) from e

            except requests.exceptions.RequestException as e:
                # Other request exceptions
                if retry_count < max_retries:
                    retry_count += 1
                    _logger.warning(
                        "Request error, retrying in %s seconds (attempt %s/%s): %s",
                        retry_delay,
                        retry_count,
                        max_retries + 1,
                        str(e),
                    )
                    import time

                    time.sleep(retry_delay)
                    continue
                else:
                    _logger.error(
                        "HTTP error in Bill.com API request after %s attempts: %s",
                        retry_count + 1,
                        str(e),
                    )
                    _logger.error(
                        "Response content: %s",
                        getattr(e.response, "content", "No content"),
                    )
                    raise UserError(
                        _("HTTP error in Bill.com API request after %s attempts: %s")
                        % (retry_count + 1, str(e))
                    ) from e

            except Exception as e:
                # Unexpected errors
                if retry_count < max_retries:
                    retry_count += 1
                    _logger.warning(
                        "Unexpected error, retrying in %s seconds (attempt %s/%s): %s",
                        retry_delay,
                        retry_count,
                        max_retries + 1,
                        str(e),
                    )
                    import time

                    time.sleep(retry_delay)
                    continue
                else:
                    _logger.error(
                        "Unexpected error in Bill.com API request after %s attempts: %s",
                        retry_count + 1,
                        str(e),
                    )
                    raise UserError(
                        _(
                            "Unexpected error in Bill.com API request after %s attempts: %s"
                        )
                        % (retry_count + 1, str(e))
                    ) from e

            try:
                if response.status_code >= 400:
                    _logger.error(
                        "HTTP error in Bill.com API request: %s", response.status_code
                    )
                    _logger.error("Response content: %s", response.content)
                    try:
                        error_data = response.json()
                        _logger.error("Error response JSON: %s", error_data)
                    except Exception as e:
                        _logger.error(
                            "Could not parse error response as JSON: %s", str(e)
                        )
                        error_data = {"errorMessage": response.text}

                    # Determine if this error is retryable
                    if (
                        response.status_code in (429, 500, 502, 503, 504)
                        and retry_count < max_retries
                    ):
                        retry_count += 1
                        _logger.warning(
                            "Retryable error status %s, retrying in %s seconds "
                            "(attempt %s/%s)",
                            response.status_code,
                            retry_delay,
                            retry_count,
                            max_retries + 1,
                        )
                        import time

                        time.sleep(retry_delay)
                        continue
                    else:
                        error_message = error_data.get("errorMessage", "Unknown error")
                        raise UserError(
                            _("Bill.com API error after %s attempts: %s")
                            % (retry_count + 1, error_message)
                        )

                response.raise_for_status()

                if not response.content or not response.content.strip():
                    return {}

                result = response.json()
                _logger.debug("Response JSON: %s", result)

                if isinstance(result, dict) and result.get("status") == "error":
                    error_message = result.get("errorMessage", "Unknown error")
                    _logger.error("Bill.com API error: %s", error_message)

                    # Check if we should retry
                    if retry_count < max_retries:
                        retry_count += 1
                        _logger.warning(
                            "API returned error, retrying in %s seconds (attempt %s/%s): %s",
                            retry_delay,
                            retry_count,
                            max_retries + 1,
                            error_message,
                        )
                        import time

                        time.sleep(retry_delay)
                        continue
                    else:
                        raise UserError(
                            _("Bill.com API error after %s attempts: %s")
                            % (retry_count + 1, error_message)
                        )

                # If we get here, the request was successful
                return result

            except ValueError as e:
                # JSON parsing error
                _logger.error("Error parsing JSON response: %s", str(e))
                _logger.error("Response content: %s", response.content)

                if retry_count < max_retries:
                    retry_count += 1
                    _logger.warning(
                        "JSON parsing error, retrying in %s seconds (attempt %s/%s): %s",
                        retry_delay,
                        retry_count,
                        max_retries + 1,
                        str(e),
                    )
                    import time

                    time.sleep(retry_delay)
                    continue
                else:
                    raise UserError(
                        _("Error parsing JSON response after %s attempts: %s")
                        % (retry_count + 1, str(e))
                    ) from e

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
