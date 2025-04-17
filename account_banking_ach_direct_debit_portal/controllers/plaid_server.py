import logging

import requests

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class PlaidServerController(http.Controller):
    @http.route(
        "/payment/plaid/get_link_token",
        type="json",
        auth="public",
        methods=["POST"],
        cors="*",
    )
    def get_link_token(self, provider_id=None, transaction_id=None):
        """Genera un link_token de Plaid para Transfer."""
        plaid_env = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("account_banking_ach_direct_debit_portal.plaid_env", "sandbox")
        )

        plaid_client_id = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("account_banking_ach_direct_debit_portal.plaid_client_id")
        )

        plaid_secret = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("account_banking_ach_direct_debit_portal.plaid_secret")
        )

        plaid_url = {
            "sandbox": "https://sandbox.plaid.com",
            "development": "https://development.plaid.com",
            "production": "https://production.plaid.com",
        }.get(plaid_env, "https://sandbox.plaid.com")

        payload = {
            "client_id": plaid_client_id,
            "secret": plaid_secret,
            "user": {"client_user_id": f"odoo_user_{request.session.uid}"},
            "client_name": "Odoo Shop",
            "products": ["auth", "identity"],
            "country_codes": ["US"],
            "language": "en",
        }

        try:
            r = requests.post(
                f"{plaid_url}/link/token/create", json=payload, timeout=10
            )
            data = r.json()
            if r.status_code != 200 or "link_token" not in data:
                return {
                    "error": data.get("error_message", "Error generating link_token")
                }
            return data
        except Exception as e:
            return {"error": f"Error requesting link_token from Plaid: {str(e)}"}
