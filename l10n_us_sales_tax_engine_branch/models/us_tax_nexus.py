# Copyright 2026 Binhex - Edilio Escalona Almira.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import api, models


class UsTaxNexus(models.Model):
    _inherit = "us.tax.nexus"

    @api.model
    def has_nexus(self, company_id, state_id):
        """Let a branch rely on its own nexus or on the one of any parent."""
        return super().has_nexus(company_id, state_id) or bool(
            self.search(
                [
                    ("company_id", "parent_of", company_id),
                    ("state_id", "=", state_id),
                ],
                limit=1,
            )
        )
