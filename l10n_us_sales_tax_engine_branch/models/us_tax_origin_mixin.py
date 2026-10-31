# Copyright 2026 Binhex - Edilio Escalona Almira.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import api, fields, models


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
        "the company uses origin sourcing, unless the customer is outside the "
        "United States.",
    )
    us_tax_origin_out_of_state = fields.Boolean(
        string="Company Address Used for Out-of-State Customer",
        compute="_compute_us_tax_origin_out_of_state",
    )

    @api.depends("company_id", "partner_shipping_id")
    def _compute_us_tax_based_on_company(self):
        # The company setting and the delivery country are read on purpose
        # without depending on them: changing them must not touch existing
        # documents.
        for record in self:
            country = record.partner_shipping_id.country_id
            record.us_tax_based_on_company = bool(
                record._us_tax_origin_applicable()
                and record.company_id.us_tax_sourcing == "origin"
                and (not country or country.code == "US")
            )

    @api.depends(
        "us_tax_based_on_company",
        "company_id.state_id",
        "partner_shipping_id.state_id",
    )
    def _compute_us_tax_origin_out_of_state(self):
        for record in self:
            shipping_state = record.partner_shipping_id.state_id
            record.us_tax_origin_out_of_state = bool(
                record.us_tax_based_on_company
                and shipping_state
                and shipping_state != record.company_id.state_id
            )

    def _us_tax_origin_applicable(self):
        """Tell whether origin sourcing can apply to this kind of document."""
        self.ensure_one()
        return True
