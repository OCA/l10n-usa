# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import fields, models
from odoo.exceptions import UserError

from ..services import ser_builder


class UsTaxReturn(models.Model):
    _inherit = "us.tax.return"

    state_registration_id = fields.Char(
        string="State Registration ID",
        help="State-issued seller ID, used on the SER instead of the SST ID "
        "for sellers that are not SST-registered.",
    )

    def action_export_ser(self):
        """Export this return as an SST Simplified Electronic Return (XML)."""
        self.ensure_one()
        if self.state == "draft" or not self.line_ids:
            raise UserError(self.env._("Generate the return before exporting a SER."))
        if not (self.company_id.sst_id or self.state_registration_id):
            raise UserError(
                self.env._(
                    "Set an SST ID on the company (Settings → US Tax) or a "
                    "State Registration ID on this return before exporting a SER."
                )
            )
        if not self.company_id.sst_fein:
            raise UserError(
                self.env._(
                    "Set the company FEIN (Settings → US Tax) before exporting a "
                    "SER — it is a required filer-identity field."
                )
            )
        if not ser_builder._state_fips(self):
            raise UserError(
                self.env._(
                    "No FIPS code for %s — import the SST Rate & Boundary data "
                    "for this state first.",
                    self.state_id.code,
                )
            )

        xml_bytes = ser_builder.build_ser(self)
        filename = f"ser_{self.state_id.code}_{self.date_from}_{self.date_to}.xml"
        return self._download_attachment(filename, xml_bytes, "application/xml")
