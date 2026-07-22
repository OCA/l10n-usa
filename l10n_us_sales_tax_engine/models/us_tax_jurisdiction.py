# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class UsTaxJurisdiction(models.Model):
    _name = "us.tax.jurisdiction"
    _description = "US Tax Jurisdiction"
    _parent_name = "parent_id"
    _parent_store = True
    _rec_name = "complete_name"
    _order = "state_id, type, name"

    name = fields.Char(required=True, index=True)
    complete_name = fields.Char(
        compute="_compute_complete_name",
        store=True,
        recursive=True,
    )
    type = fields.Selection(
        [
            ("state", "State"),
            ("county", "County"),
            ("city", "City"),
            ("district", "Special District"),
        ],
        required=True,
        index=True,
    )
    state_id = fields.Many2one(
        "res.country.state",
        domain=[("country_id.code", "=", "US")],
        index=True,
        required=True,
    )
    county = fields.Char(index=True)
    city = fields.Char(index=True)
    district_code = fields.Char()
    parent_id = fields.Many2one(
        "us.tax.jurisdiction",
        string="Parent Jurisdiction",
        index=True,
        ondelete="restrict",
    )
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many("us.tax.jurisdiction", "parent_id")
    rate_ids = fields.One2many("us.tax.rate", "jurisdiction_id")
    zip_mapping_ids = fields.One2many("us.tax.zip.mapping", "jurisdiction_id")
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "unique_jurisdiction",
            "UNIQUE(state_id, type, county, city, district_code)",
            "A jurisdiction with these parameters already exists.",
        ),
    ]

    @api.depends("name", "parent_id.complete_name")
    def _compute_complete_name(self):
        for rec in self:
            if rec.parent_id:
                rec.complete_name = f"{rec.parent_id.complete_name} / {rec.name}"
            else:
                rec.complete_name = rec.name

    @api.constrains("type", "parent_id")
    def _check_parent_type(self):
        order = {"state": 0, "county": 1, "city": 2, "district": 3}
        for rec in self:
            if rec.parent_id:
                if order.get(rec.parent_id.type, 99) >= order.get(rec.type, 99):
                    raise ValidationError(
                        self.env._(
                            'Parent type "%(parent)s" must be higher in hierarchy'
                            ' than "%(child)s".',
                            parent=rec.parent_id.type,
                            child=rec.type,
                        )
                    )
