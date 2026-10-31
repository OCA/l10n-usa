# Copyright 2026 Binhex - Edilio Escalona Almira.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.l10n_us_sales_tax_engine.services.address_resolver import (
    normalize_zip,
)


class ResCompany(models.Model):
    _inherit = "res.company"

    us_tax_sourcing = fields.Selection(
        [
            ("destination", "Destination (customer address)"),
            ("origin", "Origin (company address)"),
        ],
        string="US Tax Sourcing",
        default="destination",
        required=True,
        help="Address used by default to rate the US sales tax of new sales "
        "orders and customer invoices. Destination: the customer's delivery "
        "address. Origin: the company address, except for customers outside "
        "the United States. It can be changed on each draft document.",
    )

    @api.constrains("us_tax_sourcing", "zip", "state_id", "country_id")
    def _check_us_tax_sourcing(self):
        for company in self.filtered(lambda c: c.us_tax_sourcing == "origin"):
            if not company._us_tax_has_us_address():
                raise ValidationError(
                    self.env._(
                        "Company %(company)s needs a 5-digit ZIP, a state and "
                        "United States as country to use origin-based US tax "
                        "sourcing.",
                        company=company.display_name,
                    )
                )

    def _us_tax_has_us_address(self):
        """Tell whether the company address can be used to rate US sales tax."""
        self.ensure_one()
        return bool(
            self.country_id.code == "US"
            and self.state_id
            and normalize_zip(self.zip or "")
        )
