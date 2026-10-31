# Copyright 2026 Binhex - Edilio Escalona Almira.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import logging

from odoo import api, models

from odoo.addons.l10n_us_sales_tax_engine.services.address_resolver import (
    _partner_to_address,
)

_logger = logging.getLogger(__name__)


class UsTaxEngineService(models.AbstractModel):
    _inherit = "us.tax.engine.service"

    @api.model
    def calculate_for_sale_order(self, order):
        """Rate the order with its company address when it asks for it."""
        company = self._us_tax_origin_company(order)
        if company:
            self = self.with_context(us_tax_origin_company_id=company.id)
        return super().calculate_for_sale_order(order)

    @api.model
    def calculate_for_invoice(self, move):
        """Rate the invoice with its company address when it asks for it."""
        company = self._us_tax_origin_company(move)
        if company:
            self = self.with_context(us_tax_origin_company_id=company.id)
        return super().calculate_for_invoice(move)

    @api.model
    def _us_tax_origin_company(self, record):
        """Return the company whose address rates the document, if any.

        Customers outside the United States keep the engine's behaviour
        (no tax). A company without a complete US address cannot be used:
        the document falls back to the customer address.
        """
        company = record.company_id
        if not record.us_tax_based_on_company:
            return company.browse()
        country = (record.partner_shipping_id or record.partner_id).country_id
        if country and country.code != "US":
            return company.browse()
        if not company.sudo()._us_tax_has_us_address():
            _logger.warning(
                "US tax: company %(company)s has no complete US address, "
                "%(model)s %(id)s is rated with the customer address",
                {
                    "company": company.display_name,
                    "model": record._name,
                    "id": record.id,
                },
            )
            return company.browse()
        return company

    @api.model
    def _process(
        self,
        res_model,
        res_id,
        address,
        lines,
        doc_date,
        company_id,
        currency_id,
        apply_fn,
        partner=None,
    ):
        origin_company_id = self.env.context.get("us_tax_origin_company_id")
        if origin_company_id:
            company = self.env["res.company"].sudo().browse(origin_company_id)
            address = _partner_to_address(company.partner_id)
        return super()._process(
            res_model,
            res_id,
            address,
            lines,
            doc_date,
            company_id,
            currency_id,
            apply_fn,
            partner=partner,
        )

    @api.model
    def _get_or_create_state_tax(self, state_code, company, rate_pct=0.0):
        """Name the tax after the state whose rate was applied."""
        origin_company_id = self.env.context.get("us_tax_origin_company_id")
        if origin_company_id:
            origin_company = self.env["res.company"].sudo().browse(origin_company_id)
            state_code = origin_company.state_id.code
        return super()._get_or_create_state_tax(state_code, company, rate_pct=rate_pct)
