from odoo import fields, models

from odoo.addons.crm.models.crm_lead import PARTNER_ADDRESS_FIELDS_TO_SYNC

PARTNER_ADDRESS_FIELDS_TO_SYNC.extend(["county_id"])


class Lead(models.Model):
    _inherit = "crm.lead"

    county_id = fields.Many2one(
        "res.country.state.county",
        compute="_compute_partner_address_values",
        domain="[('state_id', '=', state_id)]",
        ondelete="restrict",
        readonly=False,
        store=True,
    )

    # Override
    def _prepare_customer_values(self, partner_name, is_company, parent_id=False):
        values = super()._prepare_customer_values(partner_name, is_company, parent_id)
        values["county_id"] = self.county_id.id
        return values
