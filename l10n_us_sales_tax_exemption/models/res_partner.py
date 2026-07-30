# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    us_tax_exemption_ids = fields.One2many(
        "us.tax.exemption",
        "partner_id",
        string="US Tax Exemptions",
    )
    us_tax_exemption_count = fields.Integer(compute="_compute_us_tax_exemption_count")

    @api.depends("us_tax_exemption_ids")
    def _compute_us_tax_exemption_count(self):
        data = self.env["us.tax.exemption"]._read_group(
            [("partner_id", "in", self.ids)],
            groupby=["partner_id"],
            aggregates=["__count"],
        )
        counts = {partner.id: count for partner, count in data}
        for partner in self:
            partner.us_tax_exemption_count = counts.get(partner.id, 0)
