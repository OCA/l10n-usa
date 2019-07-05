# Copyright 2018 Thinkwell Designs <dave@thinkwelldesigns.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import api, SUPERUSER_ID


def update_bank_journals(cr, registry):
    with api.Environment.manage():
        env = api.Environment(cr, SUPERUSER_ID, {})
        journals = env['account.journal'].search([('type', '=', 'bank')])
        ach_ct = env.ref(
            'account_banking_ach_credit_transfer.ach_credit_transfer',
            raise_if_not_found=False)
        if ach_ct:
            journals.write({'outbound_payment_method_ids': [(4, ach_ct.id)]})
    return
