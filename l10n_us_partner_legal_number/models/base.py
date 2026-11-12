import re

from stdnum.ca import bn
from stdnum.exceptions import InvalidFormat, ValidationError
from stdnum.us import ein, ssn
from stdnum.util import clean

from odoo import api, fields, models
from odoo.exceptions import UserError

# stdnum.us.ein's own format: two digits, optional separator, seven digits.
_EIN_RE = re.compile(r"^[0-9]{2}-?[0-9]{7}$")


def _validate_ein(number):
    """Validate a US EIN, falling back to the format check alone.

    ``ein.validate`` ends in a lookup of ``us/ein.dat``, which Odoo 19's
    monkeypatched stdnum loader cannot read; the campus-prefix check goes
    with it.
    """
    try:
        return ein.validate(number)
    except OSError:
        if not _EIN_RE.match(clean(number, "").strip()):
            raise InvalidFormat() from None
        return ein.compact(number)


class LegalIDNumber(models.AbstractModel):
    """
    Odoo's VAT field validation prevents it from being used
    for EIN / GST / SSN, etc.

    Use generic ID and apply validation depending on the Country field.
    """

    _name = "countinghouse.legal_id_number"
    _description = "Counting House Legal Id Number"

    legal_id_number = fields.Char(
        string="Legal ID",
        required=False,
        help="""For US entities, enter valid EIN or Social Security Number.
        Canadian entities, enter Canadian Business Number.
        """,
    )

    @api.constrains("legal_id_number")
    def validate_legal_id_number(self):
        for record in self:
            number = record.legal_id_number
            if not number:
                continue
            for validate in (ssn.validate, _validate_ein, bn.validate):
                try:
                    validate(number)
                    break
                except ValidationError:
                    continue
            else:
                raise UserError(
                    self.env._(
                        "%s is not a valid EIN / SSN / Canadian Business Number",
                        number,
                    )
                )
