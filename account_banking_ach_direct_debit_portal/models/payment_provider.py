# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class PaymentProvider(models.Model):
    _inherit = "payment.provider"

    fa_icon = fields.Char()
    code = fields.Selection(
        selection_add=[("ach_bank_account", "ACH Bank Account")],
        ondelete={"ach_bank_account": "set default"},
    )

    @api.model
    def _get_compatible_providers(self, *args, currency_id=None, **kwargs):
        providers = super()._get_compatible_providers(
            *args, currency_id=currency_id, **kwargs
        )
        include_ach_bank_account = kwargs.get("include_ach_bank_account", False)
        if not include_ach_bank_account:
            providers = providers.filtered(lambda p: p.code != "ach_bank_account")
        return providers
