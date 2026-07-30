# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    sst_id = fields.Char(
        string="SST ID (SSTPID)",
        help="Streamlined Sales Tax registration ID issued by the SSTRS "
        "(format S followed by 8 digits). Used as the SER filer identity for "
        "SST-registered sellers.",
    )
    sst_fein = fields.Char(
        string="FEIN",
        help="Federal Employer Identification Number reported on the SER.",
    )
    sst_transmitter_id = fields.Char(
        string="SST Transmitter ID",
        help="Identifier assigned to the transmitter; prefixes the SER TransmissionId.",
    )
    sst_test_mode = fields.Boolean(
        string="SST Test Transmission",
        default=True,
        help="When set, the SER ProcessType is 'T' (test). Disable to produce a "
        "production ('P') transmission.",
    )
    sst_transmission_version = fields.Char(
        string="SER Schema Version",
        default="SSTSER2025V01",
        help="transmissionVersion emitted on the SER. Confirm the value against "
        "the target state's / FTA E-Standards published XSD before live filing.",
    )
