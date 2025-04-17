from odoo import api, fields, models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    contact_bank_id = fields.Many2one(
        "res.partner.bank",
        string="Partner Bank Account",
        readonly=False,
        store=True,
        domain="[('id', 'in', available_contact_bank_ids)]",
        check_company=True,
    )

    available_contact_bank_ids = fields.Many2many(
        comodel_name="res.partner.bank",
        compute="_compute_available_contact_bank_ids",
    )

    @api.depends("partner_id")
    def _compute_available_contact_bank_ids(self):
        for pay in self:
            pay.available_contact_bank_ids = pay.partner_id.bank_ids.filtered(
                lambda x: x.company_id.id in (False, pay.company_id.id)
            )._origin
