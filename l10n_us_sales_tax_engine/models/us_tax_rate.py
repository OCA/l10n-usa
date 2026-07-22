# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class UsTaxRate(models.Model):
    _name = "us.tax.rate"
    _description = "US Tax Rate (Versioned)"
    _order = "jurisdiction_id, effective_date desc"

    jurisdiction_id = fields.Many2one(
        "us.tax.jurisdiction",
        required=True,
        index=True,
        ondelete="restrict",
    )
    state_id = fields.Many2one(
        related="jurisdiction_id.state_id",
        store=True,
        index=True,
    )
    product_tax_category_id = fields.Many2one(
        "us.tax.product.category",
        help="Leave empty to apply to all categories.",
    )
    state_rate = fields.Float(digits=(5, 4), default=0.0)
    county_rate = fields.Float(digits=(5, 4), default=0.0)
    city_rate = fields.Float(digits=(5, 4), default=0.0)
    district_rate = fields.Float(digits=(5, 4), default=0.0)
    total_rate = fields.Float(
        digits=(5, 4),
        compute="_compute_total_rate",
        store=True,
        help="Sum of all rate components.",
    )
    effective_date = fields.Date(required=True, index=True)
    end_date = fields.Date(
        index=True,
        help="Leave empty if this rate is currently in effect.",
    )
    source = fields.Char(
        default="manual",
        help="Origin: e.g. florida_dor, manual, or the code of an "
        "external provider module.",
    )
    source_url = fields.Char(string="Source URL")
    import_batch_id = fields.Many2one("us.tax.import.batch")
    notes = fields.Text()
    active = fields.Boolean(default=True)

    @api.depends("state_rate", "county_rate", "city_rate", "district_rate")
    def _compute_total_rate(self):
        for rec in self:
            rec.total_rate = round(
                rec.state_rate + rec.county_rate + rec.city_rate + rec.district_rate, 6
            )

    @api.constrains("effective_date", "end_date")
    def _check_dates(self):
        for rec in self:
            if rec.end_date and rec.effective_date > rec.end_date:
                raise ValidationError(
                    self.env._("Effective date must be before or equal to end date.")
                )

    @api.model
    def get_rate_for_date(self, jurisdiction_id, date, product_category_id=None):
        """Return the rate valid on a given date for a jurisdiction.

        Preference: specific product category > generic (null category).
        A category-specific rate is tried first when one is requested; if
        none exists, falls back to the generic rate rather than returning
        nothing — a jurisdiction is rarely imported with a rate row for
        every category.
        """
        base_domain = [
            ("jurisdiction_id", "=", jurisdiction_id),
            ("effective_date", "<=", date),
            "|",
            ("end_date", "=", False),
            ("end_date", ">=", date),
        ]
        if product_category_id:
            rate = self.search(
                base_domain + [("product_tax_category_id", "=", product_category_id)],
                order="effective_date desc, id desc",
                limit=1,
            )
            if rate:
                return rate
        return self.search(
            base_domain + [("product_tax_category_id", "=", False)],
            order="effective_date desc, id desc",
            limit=1,
        )
