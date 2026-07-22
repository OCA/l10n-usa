# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import api, fields, models


class UsTaxZipMapping(models.Model):
    _name = "us.tax.zip.mapping"
    _description = "US Tax ZIP to Jurisdiction Mapping"
    _order = "zip, confidence desc"
    _rec_name = "zip"

    zip = fields.Char(
        string="ZIP Code",
        size=5,
        required=True,
        index=True,
    )
    zip4 = fields.Char(string="ZIP+4", size=4)
    state_id = fields.Many2one(
        "res.country.state",
        domain=[("country_id.code", "=", "US")],
        required=True,
        index=True,
    )
    jurisdiction_id = fields.Many2one(
        "us.tax.jurisdiction",
        required=True,
        index=True,
        ondelete="restrict",
    )
    county = fields.Char()
    city = fields.Char()
    confidence = fields.Float(
        default=1.0,
        help="Confidence 0.0-1.0. Highest wins when ZIP has multiple jurisdictions.",
    )
    source = fields.Char(
        default="manual",
        help="Data origin: florida_dor, texas_open_data, api_ziptax, manual",
    )
    imported_at = fields.Datetime(default=fields.Datetime.now)
    import_batch_id = fields.Many2one("us.tax.import.batch")

    _sql_constraints = [
        (
            "zip_jurisdiction_unique",
            "UNIQUE(zip, jurisdiction_id)",
            "This ZIP + Jurisdiction combination already exists.",
        ),
    ]

    @api.model
    def get_best_jurisdiction(self, zip_code, state_code=None, confidence_min=0.7):
        """Return the best jurisdiction for a ZIP code.

        Args:
            zip_code: 5-digit ZIP string
            state_code: Optional 2-letter state code to narrow down
            confidence_min: Minimum confidence threshold
        Returns:
            us.tax.jurisdiction record or empty recordset
        """
        domain = [
            ("zip", "=", zip_code),
            ("confidence", ">=", confidence_min),
        ]
        if state_code:
            domain += [("state_id.code", "=", state_code)]

        mapping = self.search(domain, order="confidence desc", limit=1)
        return mapping.jurisdiction_id if mapping else self.env["us.tax.jurisdiction"]
