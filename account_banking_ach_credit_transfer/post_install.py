from odoo import api, SUPERUSER_ID


def update_bank_journals(cr, registry):
    with api.Environment.manage():
        env = api.Environment(cr, SUPERUSER_ID, {})
        journals = env['account.journal'].search([('type', '=', 'bank')])
        ach_ct = env.ref('account_banking_ach_credit_transfer.ach_credit_transfer')
        if ach_ct:
            journals.write({
                'outbound_payment_method_ids': [(4, ach_ct.id)],
            })
    return
