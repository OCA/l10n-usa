# Copyright 2026 Binhex - Edilio Escalona Almira.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    us_tax_sourcing = fields.Selection(
        related="company_id.us_tax_sourcing",
        readonly=False,
    )
