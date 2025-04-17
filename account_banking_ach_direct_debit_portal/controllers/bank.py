import traceback

from plaid.api import plaid_api
from plaid.api_client import ApiClient
from plaid.configuration import Configuration
from plaid.model.auth_get_request import AuthGetRequest
from plaid.model.identity_get_request import IdentityGetRequest
from plaid.model.item_public_token_exchange_request import (
    ItemPublicTokenExchangeRequest,
)

from odoo import _, http
from odoo.exceptions import AccessError
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal


class BankController(CustomerPortal):
    @http.route(
        ["/my/banks"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_banks(self, **kw):
        partner = request.env.user.partner_id

        add_success = request.httprequest.args.get("add_success", 0)

        bank_accounts = request.env["res.partner.bank"].search(
            [("partner_id", "=", partner.id)], order="default DESC, id DESC"
        )

        values = {
            "page_name": "bank",
            "add_success": add_success,
            "bank_accounts": bank_accounts,
        }

        if request.session.get("edit_bank_success"):
            values["edit_bank_success"] = True
            request.session["edit_bank_success"] = False

        if request.session.get("delete_bank_success"):
            values["delete_bank_success"] = True
            request.session["delete_bank_success"] = False

        if request.session.get("set_default_bank_success"):
            values["set_default_bank_success"] = True
            request.session["set_default_bank_success"] = True

        return request.render(
            "account_banking_ach_direct_debit_portal.portal_banks", values
        )

    @http.route(
        ["/my/banks/add"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_add_bank(self, **kw):
        values = {
            "page_name": "bank",
        }

        return request.render(
            "account_banking_ach_direct_debit_portal.add_bank", values
        )

    @http.route("/my/banks/verify_submit", type="json", auth="user", csrf=False)
    def plaid_verify_submit(self):
        partner_id = request.env.user.partner_id.id

        data = request.get_json_data()

        public_token = data.get("public_token")
        account_id = data.get("account_id")

        client_id = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("account_banking_ach_direct_debit_portal.plaid_client_id")
        )
        secret = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("account_banking_ach_direct_debit_portal.plaid_secret")
        )
        plaid_env = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("account_banking_ach_direct_debit_portal.plaid_env", "sandbox")
        )

        plaid_host_map = {
            "sandbox": "https://sandbox.plaid.com",
            "development": "https://development.plaid.com",
            "production": "https://production.plaid.com",
        }

        configuration = Configuration(
            host=plaid_host_map.get(plaid_env, "https://sandbox.plaid.com"),
            api_key={
                "clientId": client_id,
                "secret": secret,
            },
        )
        api_client = ApiClient(configuration)
        client = plaid_api.PlaidApi(api_client)

        try:
            # Exchange public_token for access_token
            exchange_request = ItemPublicTokenExchangeRequest(public_token=public_token)
            exchange_response = client.item_public_token_exchange(exchange_request)
            access_token = exchange_response.access_token

            # Retrieve account info using Auth.get
            auth_request = AuthGetRequest(access_token=access_token)
            auth_response = client.auth_get(auth_request)

            institution_id = auth_response["item"]["institution_id"]
            institution_name = auth_response["item"]["institution_name"]

            bank = request.env["res.bank"].search(
                [("plaid_institution_id", "=", institution_id)], limit=1
            )

            if not bank:
                bank = request.env["res.bank"].create(
                    {
                        "name": institution_name,
                        "plaid_institution_id": institution_id,
                    }
                )

            accounts = auth_response.accounts

            account = next((a for a in accounts if a.account_id == account_id), None)
            if not account:
                return {"status": "error", "error": "Bank account not found"}

            identity_request = IdentityGetRequest(access_token=access_token)
            identity_response = client.identity_get(identity_request)
            identity_accounts = identity_response.accounts

            routing_number = None

            ach_numbers = auth_response.numbers.ach
            for ach in ach_numbers:
                acc_number = ach.account
                aba_routing = ach.routing
                account_id = ach.account_id
                routing_number = ach.routing

                acc_holder_name = None
                for identity_acc in identity_accounts:
                    if identity_acc.account_id == account_id and identity_acc.owners:
                        acc_holder_name = identity_acc.owners[0].names[0]
                        break

                bank_rec = request.env["res.partner.bank"].search(
                    [
                        ("acc_number", "=", acc_number),
                        ("aba_routing", "=", aba_routing),
                        ("partner_id", "=", partner_id),
                    ],
                    limit=1,
                )

                if not bank_rec:
                    bank_rec = request.env["res.partner.bank"].create(
                        {
                            "acc_holder_name": acc_holder_name or "Unknown",
                            "acc_number": acc_number,
                            "bank_id": bank.id,
                            "aba_routing": aba_routing,
                            "partner_id": partner_id,
                            "acc_type": "normal",
                            "verified": True,
                        }
                    )

            if not bank.routing_number and routing_number:
                bank.write({"routing_number": routing_number})

            return {"status": "success"}

        except Exception as e:
            # Optional: include traceback for debugging
            error_msg = f"{str(e)}\n{traceback.format_exc()}"
            return {"status": "error", "error": error_msg}

    @http.route(
        "/my/banks/delete/<int:bank_id>",
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
    )
    def portal_delete_bank(self, bank_id, **kw):
        partner = request.env.user.partner_id
        partner_bank = request.env["res.partner.bank"].browse(bank_id)

        if not partner_bank.exists() or partner_bank.partner_id.id != partner.id:
            raise AccessError(
                _("You do not have permission to edit this bank account.")
            )

        bank = partner_bank.bank_id

        bank.unlink()
        partner_bank.unlink()

        request.session["delete_bank_success"] = True

        return request.redirect("/my/banks")

    @http.route(
        "/my/banks/edit/<int:bank_id>",
        type="http",
        auth="user",
        website=True,
        methods=["GET", "POST"],
    )
    def portal_edit_bank(self, bank_id, **kw):
        partner = request.env.user.partner_id
        partner_bank = request.env["res.partner.bank"].browse(bank_id)

        if not partner_bank.exists() or partner_bank.partner_id.id != partner.id:
            raise AccessError(
                _("You do not have permission to edit this bank account.")
            )

        acc_type_choices = request.env[
            "res.partner.bank"
        ]._get_supported_account_types()

        if request.httprequest.method == "POST":
            bank = partner_bank.bank_id

            if bank:
                bank.write(
                    {
                        "name": kw.get("bank_name"),
                        "street": kw.get("bank_address"),
                    }
                )
            else:
                bank = request.env["res.bank"].create(
                    {
                        "name": kw.get("bank_name"),
                        "street": kw.get("bank_address"),
                    }
                )

            partner_bank.write(
                {
                    "acc_holder_name": kw.get("acc_holder_name"),
                    "acc_number": kw.get("acc_number"),
                    "bank_id": bank.id,
                    "aba_routing": kw.get("routing_number"),
                    "acc_type": kw.get("acc_type"),
                }
            )

            request.session["edit_bank_success"] = True

            return request.redirect("/my/banks")

        return request.render(
            "account_banking_ach_direct_debit_portal.portal_bank_form",
            {
                "acc_type_choices": acc_type_choices,
                "bank": partner_bank,
                "edit_mode": True,
                "page_name": "bank",
            },
        )

    @http.route(
        "/my/bank/set_default/<int:bank_id>", type="http", auth="user", methods=["GET"]
    )
    def set_default_bank(self, bank_id):
        bank = request.env["res.partner.bank"].browse(bank_id)
        if not bank.exists():
            return request.redirect("/my/banks")
        if bank.partner_id != request.env.user.partner_id:
            raise AccessError(_("You do not have permission to modify this bank."))

        bank.write({"default": True})

        request.session["set_default_bank_success"] = True

        return request.redirect("/my/banks")
