# Copyright 2026 Binhex - Edilio Escalona Almira.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import api, fields, models

from odoo.addons.l10n_us_sales_tax_engine.services.address_resolver import (
    resolve_shipping_address,
)


class UsTaxOriginMixin(models.AbstractModel):
    _name = "us.tax.origin.mixin"
    _description = "US Tax Origin Sourcing Mixin"

    us_tax_based_on_company = fields.Boolean(
        string="Tax Based on Company Address",
        compute="_compute_us_tax_based_on_company",
        store=True,
        readonly=False,
        copy=True,
        help="Rate US sales tax with the address of the document's company "
        "instead of the customer's delivery address. Checked by default when "
        "the company uses origin sourcing and the delivery address is in the "
        "company's state or has no state.",
    )
    us_tax_origin_out_of_state = fields.Boolean(
        string="Company Address Used for Out-of-State Customer",
        compute="_compute_us_tax_origin_out_of_state",
    )
    us_tax_origin_address_missing = fields.Boolean(
        string="Company Address Incomplete for US Tax",
        compute="_compute_us_tax_origin_address_missing",
    )

    @api.depends("company_id", "partner_id", "partner_shipping_id")
    def _compute_us_tax_based_on_company(self):
        # The company setting and the delivery address are read on purpose
        # without depending on their fields: changing them must not touch
        # existing documents.
        for record in self:
            address = resolve_shipping_address(record)
            country_code = address.get("country_code")
            state_code = address.get("state")
            record.us_tax_based_on_company = bool(
                record._us_tax_origin_applicable()
                and record.company_id.us_tax_sourcing == "origin"
                and (not country_code or country_code == "US")
                and (not state_code or state_code == record.company_id.state_id.code)
            )

    @api.depends(
        "us_tax_based_on_company",
        "company_id.state_id",
        "partner_id.state_id",
        "partner_shipping_id.state_id",
    )
    def _compute_us_tax_origin_out_of_state(self):
        for record in self:
            state_code = resolve_shipping_address(record).get("state")
            record.us_tax_origin_out_of_state = bool(
                record.us_tax_based_on_company
                and state_code
                and state_code != record.company_id.state_id.code
            )

    @api.depends(
        "us_tax_based_on_company",
        "company_id.zip",
        "company_id.state_id",
        "company_id.country_id",
    )
    def _compute_us_tax_origin_address_missing(self):
        for record in self:
            record.us_tax_origin_address_missing = bool(
                record.us_tax_based_on_company
                and not record.company_id.sudo()._us_tax_has_us_address()
            )

    def _us_tax_origin_applicable(self):
        """Tell whether origin sourcing can apply to this kind of document."""
        self.ensure_one()
        return True
