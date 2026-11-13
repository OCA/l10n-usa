# Copyright 2026 Binhex - Edilio Escalona Almira.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import api, fields, models


class UsTaxCalculationLog(models.Model):
    _inherit = "us.tax.calculation.log"

    us_tax_sourcing = fields.Selection(
        [("destination", "Destination"), ("origin", "Origin")],
        string="Tax Sourcing",
        default="destination",
        readonly=True,
        help="Whose address was used: the customer's (destination) or the "
        "document company's (origin).",
    )

    @api.model
    def log_calculation(self, payload):
        """Record whether the rated address was the company's."""
        if self.env.context.get("us_tax_origin_company_id"):
            payload = dict(payload, us_tax_sourcing="origin")
        return super().log_calculation(payload)
