# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class UsTaxRule(models.Model):
    _name = "us.tax.rule"
    _description = "US Tax Rule (State/Category Taxability)"
    _order = "state_id, product_tax_category_id"

    state_id = fields.Many2one(
        "res.country.state",
        domain=[("country_id.code", "=", "US")],
        help="Leave empty to apply to all US states.",
    )
    product_tax_category_id = fields.Many2one(
        "us.tax.product.category",
        required=True,
        ondelete="restrict",
    )
    taxable = fields.Boolean(
        default=True,
        help="Is this category taxable in this state?",
    )
    rate_override = fields.Float(
        digits=(5, 4),
        help="If set, use this rate instead of the standard jurisdiction rate.",
    )
    exemption_reason = fields.Char(
        help="Legal or regulatory basis for exemption.",
    )
    effective_date = fields.Date()
    end_date = fields.Date()
    active = fields.Boolean(default=True)

    @api.constrains("effective_date", "end_date")
    def _check_dates(self):
        for rec in self:
            if rec.effective_date and rec.end_date:
                if rec.effective_date > rec.end_date:
                    raise ValidationError(
                        self.env._("Effective date must be before end date.")
                    )

    @api.model
    def is_taxable(self, state_id, product_category_id, date=None):
        """Check if a product category is taxable in a state on a given date.

        Returns:
            (taxable: bool, rate_override: float | None)
        """
        # If no category resolved → default to taxable (physical goods assumption)
        if not product_category_id:
            return True, None

        domain = [
            ("product_tax_category_id", "=", product_category_id),
            "|",
            ("state_id", "=", state_id),
            ("state_id", "=", False),
        ]
        if date:
            domain += [
                "|",
                ("effective_date", "=", False),
                ("effective_date", "<=", date),
                "|",
                ("end_date", "=", False),
                ("end_date", ">=", date),
            ]
        # State-specific rule takes priority over global rule
        rule = self.search(domain, order="state_id desc", limit=1)
        if rule:
            return rule.taxable, rule.rate_override or None
        # Default: use product category's default_taxable
        category = self.env["us.tax.product.category"].browse(product_category_id)
        if not category.exists():
            return True, None  # Unknown category → taxable by default
        return category.default_taxable, None
