# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import api, models


class UsTaxEngineService(models.AbstractModel):
    _inherit = "us.tax.engine.service"

    @api.model
    def _get_marketplace_collection(self, res_model, res_id):
        """Return the marketplace code if the document is facilitator-collected."""
        if res_model not in ("sale.order", "account.move"):
            return False
        record = self.env[res_model].browse(res_id)
        marketplace = record.us_tax_marketplace_id
        return marketplace.code if marketplace else False
