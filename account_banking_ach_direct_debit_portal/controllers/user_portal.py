from odoo import http
from odoo.http import request


class UserPortalController(http.Controller):
    @staticmethod
    def is_ach_accessible():
        return request.env.user.is_ach_portal_enabled_for_user()

    @staticmethod
    def deny_403():
        return request.render(
            "account_banking_ach_direct_debit_portal.alert_portal_403_template"
        )
