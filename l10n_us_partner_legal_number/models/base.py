from stdnum.ca import bn
from stdnum.us import ein, ssn

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class LegalIDNumber(models.AbstractModel):
    """
    Odoo's VAT field validation prevents it from being used
    for EIN / GST / SSN, etc.

    Use generic ID and apply validation depending on the Country field.
    """

    _name = "countinghouse.legal_id_number"
    _description = "Countinghouse Legal Id Number"

    legal_id_number = fields.Char(
        string="Legal ID",
        required=False,
        help="""For US entities, enter valid EIN or Social Security Number.
        Canadian entities, enter Canadian Business Number.
        """,
    )

    @api.constrains("legal_id_number")
    def validate_legal_id_number(self):
        if not self.legal_id_number:
            return
        valid = False
        for v in (ssn, ein, bn):
            try:
                v.validate(self.legal_id_number)
                valid = True
                break
            except Exception:
                continue
        if not valid:
            raise UserError(
                _(
                    "%s is not a valid EIN / SSN / Canadian Business "
                    "Number" % self.legal_id_number
                )
            )
