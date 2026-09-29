# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class UsTaxEngineService(models.AbstractModel):
    _inherit = "us.tax.engine.service"

    @api.model
    def _get_origin_partner(self, res_model, res_id, company_id):
        """Origin-based sourcing ships from the document's warehouse when one
        resolves, else the company address (engine default)."""
        warehouse = self._us_tax_origin_warehouse(res_model, res_id)
        if warehouse.partner_id:
            return warehouse.partner_id
        return super()._get_origin_partner(res_model, res_id, company_id)

    @api.model
    def _us_tax_origin_warehouse(self, res_model, res_id):
        """The shipping warehouse for the document, or an empty recordset."""
        warehouse = self.env["stock.warehouse"]
        if not res_id:
            return warehouse
        record = self.env[res_model].browse(res_id)
        if res_model == "sale.order":
            return record.warehouse_id
        if res_model == "account.move" and record.move_type in (
            "out_invoice",
            "out_refund",
        ):
            # Derive from the originating sale order(s).
            warehouses = record.invoice_line_ids.sale_line_ids.order_id.warehouse_id
            if len(warehouses) > 1:
                _logger.warning(
                    "US Tax: %s consolidates %s warehouses; sourcing origin from %s.",
                    record.display_name,
                    len(warehouses),
                    warehouses[:1].name,
                )
            return warehouses[:1]
        return warehouse
