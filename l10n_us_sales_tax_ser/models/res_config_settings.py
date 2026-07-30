# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    sst_id = fields.Char(related="company_id.sst_id", readonly=False)
    sst_fein = fields.Char(related="company_id.sst_fein", readonly=False)
    sst_transmitter_id = fields.Char(
        related="company_id.sst_transmitter_id", readonly=False
    )
    sst_test_mode = fields.Boolean(related="company_id.sst_test_mode", readonly=False)
    sst_transmission_version = fields.Char(
        related="company_id.sst_transmission_version", readonly=False
    )
