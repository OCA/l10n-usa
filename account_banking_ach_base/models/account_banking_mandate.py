from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountBankingMandate(models.Model):
    _inherit = 'account.banking.mandate'

    delay_days = fields.Integer(string='Delay Days', required=True,
                                default=10,
                                help='''Number of days to wait after invoice
                                date before including an invoice in Payment
                                Order for processing.''')

    def validate(self):
        for mandate in self:
            if not mandate.delay_days:
                raise UserError(_('''Delay days must be specified, and
                greater than 0.'''))
        super(AccountBankingMandate, self).validate()

    def set_payment_modes_on_partner(self):
        """
        Set the payment modes on the Partner if they don't already exist.
        """
        payment_modes = {}
        if self.partner_id.customer and not \
                self.partner_id.customer_payment_mode_id:
            customer_mode = self.env['account.payment.mode'].search([
                ('payment_type', '=', 'inbound'),
                ('company_id', '=', self.company_id.id),
            ], limit=1)
            if customer_mode:
                payment_modes['customer_payment_mode_id'] = customer_mode.id
        if self.partner_id.supplier and not \
                self.partner_id.supplier_payment_mode_id:
            supplier_mode = self.env['account.payment.mode'].search([
                ('payment_type', '=', 'outbound'),
                ('company_id', '=', self.company_id.id),
            ], limit=1)
            if supplier_mode:
                payment_modes['supplier_payment_mode_id'] = supplier_mode.id
        if payment_modes:
            self.partner_id.write(payment_modes)

    @api.model
    def create(self, vals):
        mandate = super(AccountBankingMandate, self).create(vals)
        mandate.set_payment_modes_on_partner()
        return mandate
