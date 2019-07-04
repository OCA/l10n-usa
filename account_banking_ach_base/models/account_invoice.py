from datetime import date, timedelta
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    @api.multi
    def create_account_payment_line(self):
        today = date.today()
        for invoice in self:
            mandate = invoice.mandate_id
            if not mandate:
                continue
            invoice_date = fields.Date.from_string(invoice.date_invoice)
            delay_expired = invoice_date + timedelta(days=mandate.delay_days)
            if today < delay_expired:
                raise UserError(
                    _('To satisfy payment mandate, cannot add invoice %s to '
                      'Debit Order until %s!' %
                      (invoice.number, delay_expired.strftime('%Y-%m-%d'))))
        return super(AccountInvoice, self).create_account_payment_line()
