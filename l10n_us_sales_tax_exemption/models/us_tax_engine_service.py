# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import api, models


class UsTaxEngineService(models.AbstractModel):
    _inherit = "us.tax.engine.service"

    @api.model
    def _get_customer_exemption(self, partner_id, state, doc_date, company_id=False):
        """Return the reason code of a valid exemption, if any.

        Two triggers, most specific first:

        1. A certificate held by the customer covering ``state`` and valid on
           ``doc_date`` (effective, not expired, not revoked).
        2. A fiscal position flagged "US Tax Exempt" on the customer — the
           Odoo-native way to say "this partner is not taxed here", for
           installations that manage exemption through fiscal positions rather
           than tracking the certificates themselves.

        A certificate wins when both apply: it carries the reason and the
        certificate number an auditor asks for.
        """
        if not partner_id or not state:
            return False
        certificate = self.env["us.tax.exemption"]._resolve(
            partner_id, state, doc_date, company_id
        )
        if certificate:
            return certificate.reason_id.code
        position = (
            self.env["res.partner"].browse(partner_id).property_account_position_id
        )
        if position.is_us_tax_exempt:
            return position.us_tax_exemption_reason_id.code or "other"
        return False
