from odoo import api, fields, models


class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

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
        for wizard in self:
            wizard.available_contact_bank_ids = wizard.partner_id.bank_ids.filtered(
                lambda x: x.company_id.id in (False, wizard.company_id.id)
            )._origin

    def _create_payment_vals_from_wizard(self, batch_result):
        payment_vals = super()._create_payment_vals_from_wizard(batch_result)

        payment_vals["contact_bank_id"] = self.contact_bank_id.id

        return payment_vals
