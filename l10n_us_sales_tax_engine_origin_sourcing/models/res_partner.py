# Copyright 2026 Binhex - Edilio Escalona Almira.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import api, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    @api.constrains("zip", "state_id", "country_id")
    def _check_us_tax_sourcing(self):
        """Keep the address of an origin-sourcing company complete.

        The address fields of a company are stored on its partner, which can
        be edited without going through the company form.
        """
        companies = (
            self.env["res.company"]
            .sudo()
            .search(
                [("partner_id", "in", self.ids), ("us_tax_sourcing", "=", "origin")]
            )
        )
        companies._check_us_tax_sourcing()
