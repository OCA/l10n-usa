# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import fields, models


class UsTaxAutoMixin(models.AbstractModel):
    """US tax state shared by sale.order and account.move."""

    _name = "us.tax.auto.mixin"
    _description = "US Tax Automatic Recalculation"

    us_tax_source = fields.Char(
        string="Tax Source",
        help="Source used for the last US tax calculation.",
    )
    us_tax_calculated_at = fields.Datetime(
        string="Tax Calculated At",
    )

    def _us_tax_auto_mode(self):
        """Return the automation mode in force: off or on_validate.

        A disabled engine makes it off whatever mode is stored, because
        res.config.settings is not the only writer of ir.config_parameter
        and only a runtime check sees the pair as it is. A database that
        never chose a mode gets on_validate, which calculates on order
        confirmation and invoice posting as 18.0.1.2.x did.
        """
        ICP = self.env["ir.config_parameter"].sudo()
        if ICP.get_param("l10n_us_tax.engine_active", "False") != "True":
            return "off"
        return ICP.get_param("l10n_us_tax.auto_mode") or "on_validate"
