# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import models


class AccountMoveLine(models.Model):
    _name = "account.move.line"
    _inherit = ["us.tax.line.hash.mixin", "account.move.line"]
