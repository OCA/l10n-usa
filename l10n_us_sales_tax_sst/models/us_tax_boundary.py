# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import fields, models


class UsTaxBoundary(models.Model):
    _name = "us.tax.boundary"
    _description = "SST Address/ZIP Boundary Record"
    _order = "record_type, zip, id"
    _rec_name = "zip"

    # Record type from the SST boundary file: A=address range, 4=ZIP+4, Z=ZIP5.
    record_type = fields.Selection(
        [("A", "Address"), ("4", "ZIP+4"), ("Z", "ZIP5")],
        required=True,
        index=True,
    )
    begin_date = fields.Date(index=True)
    end_date = fields.Date(index=True, help="Empty / 2999-12-31 means open-ended.")
    # Address-range fields (record type A). Kept as strings (may be alpha PO box).
    addr_low = fields.Char()
    addr_high = fields.Char()
    odd_even = fields.Selection([("O", "Odd"), ("E", "Even"), ("B", "Both")])
    street_pre_dir = fields.Char()
    street_name = fields.Char(index=True)
    street_suffix = fields.Char()
    street_post_dir = fields.Char()
    city = fields.Char(index=True)
    # ZIP fields — strings to preserve leading zeros.
    zip = fields.Char(string="ZIP", size=5, index=True)
    zip4 = fields.Char(string="ZIP+4", size=4)
    zip_low = fields.Char(size=5, index=True)
    zip4_low = fields.Char(size=4)
    zip_high = fields.Char(size=5, index=True)
    zip4_high = fields.Char(size=4)
    fips_state = fields.Char(string="FIPS State", size=2, index=True)
    fips_county = fields.Char(string="FIPS County", size=3)
    fips_place = fields.Char(string="FIPS Place", size=5)
    state_id = fields.Many2one(
        "res.country.state",
        domain=[("country_id.code", "=", "US")],
        index=True,
    )
    # The state + county + place + special-district jurisdictions this row
    # resolves to (linked at import from the FIPS codes via the rate file).
    jurisdiction_ids = fields.Many2many(
        "us.tax.jurisdiction",
        string="Jurisdictions",
    )
    source = fields.Char(default="sst")
    import_batch_id = fields.Many2one("us.tax.import.batch")
