# Copyright 2018 Thinkwell Designs <dave@thinkwelldesigns.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

import logging
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import _, api, exceptions, fields, models
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT

NUMBER_OF_UNUSED_MONTHS_BEFORE_EXPIRY = 36

logger = logging.getLogger(__name__)


class AccountBankingMandate(models.Model):
    """ACH Direct Debit Mandate"""

    _inherit = "account.banking.mandate"

    format = fields.Selection(
        selection_add=[("ach", "ACH")], ondelete={"ach": "set default"}
    )
    type = fields.Selection(
        selection_add=[("recurrent", "Recurrent"), ("oneoff", "One-Off")],
        string="Type of Mandate",
        tracking=True,
    )
    recurrent_sequence_type = fields.Selection(
        [("first", "First"), ("recurring", "Recurring"), ("final", "Final")],
        string="Sequence Type for Next Debit",
        tracking=True,
        help="""This field is only used for Recurrent mandates, not for
        One-Off mandates.""",
        default="first",
    )
    scheme = fields.Selection(
        [("CORE", "Basic (CORE)"), ("B2B", "Enterprise (B2B)")],
        string="Scheme",
        default="CORE",
        tracking=True,
    )
    unique_mandate_reference = fields.Char(size=35)  # cf ISO 20022
    display_name = fields.Char(compute="_compute_display_name", store=True)

    @api.constrains("type", "recurrent_sequence_type")
    def _check_recurring_type(self):
        for mandate in self:
            if mandate.type == "recurrent" and not mandate.recurrent_sequence_type:
                raise exceptions.ValidationError(
                    _("The recurrent mandate '%s' must have a sequence type.")
                    % mandate.unique_mandate_reference
                )

    @api.depends("unique_mandate_reference", "recurrent_sequence_type")
    def _compute_display_name(self):
        for mandate in self:
            if mandate.format == "ach":
                name = "{} ({})".format(
                    mandate.unique_mandate_reference,
                    mandate.recurrent_sequence_type,
                )
            else:
                name = mandate.unique_mandate_reference
            mandate.display_name = name

    @api.onchange("partner_bank_id")
    def mandate_partner_bank_change(self):
        for mandate in self:
            super(AccountBankingMandate, self).mandate_partner_bank_change()
            res = {}
            if (
                mandate.state == "valid"
                and mandate.partner_bank_id
                and mandate.type == "recurrent"
                and mandate.recurrent_sequence_type != "first"
            ):
                mandate.recurrent_sequence_type = "first"
                res["warning"] = {
                    "title": _("Mandate update"),
                    "message": _(
                        "As you changed the bank account attached "
                        "to this mandate, the 'Sequence Type' has "
                        "been set back to 'First'."
                    ),
                }
            return res

    @api.model
    def _achdd_mandate_set_state_to_expired(self):
        logger.info(_("Searching for ACH Mandates that must be set to Expired"))
        expire_limit_date = datetime.today() + relativedelta(
            months=-NUMBER_OF_UNUSED_MONTHS_BEFORE_EXPIRY
        )
        expire_limit_date_str = expire_limit_date.strftime(DEFAULT_SERVER_DATE_FORMAT)
        expired_mandates = self.search(
            [
                "|",
                ("last_debit_date", "=", False),
                ("last_debit_date", "<=", expire_limit_date_str),
                ("state", "=", "valid"),
                ("signature_date", "<=", expire_limit_date_str),
            ]
        )
        if expired_mandates:
            expired_mandates.write({"state": "expired"})
            logger.info(
                _(
                    "The following ACH Mandate IDs have been set to "
                    "expired: %s" % expired_mandates.ids
                )
            )
        else:
            logger.info(_("0 ACH Mandates had to be set to Expired"))
        return True
