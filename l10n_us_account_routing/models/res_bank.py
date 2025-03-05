from stdnum.us import rtn

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ResBank(models.Model):
    _inherit = "res.bank"

    routing_number = fields.Char()

    @api.constrains("routing_number")
    def validate_routing_number(self):
        banks_filtered = self.filtered(
            lambda b: b.routing_number and b.country and b.country_code in ("US", "CA")
        )
        if not banks_filtered:
            return
        for bank in banks_filtered:
            country_code = bank.country_code
            if country_code == "US":
                if not rtn.is_valid(bank.routing_number):
                    raise ValidationError(
                        self.env._(
                            "%s is not a valid US routing number!", bank.routing_number
                        )
                    )
            elif country_code == "CA":
                if len(bank.routing_number) != 8 or not bank.routing_number.isdigit():
                    raise ValidationError(
                        self.env._(
                            "%s is not a valid Canadian routing number!",
                            bank.routing_number,
                        )
                    )
