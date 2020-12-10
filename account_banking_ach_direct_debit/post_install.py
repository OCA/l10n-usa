# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import SUPERUSER_ID, api


def update_bank_journals(cr, registry):
    with api.Environment.manage():
        env = api.Environment(cr, SUPERUSER_ID, {})
        journals = env["account.journal"].search([("type", "=", "bank")])
        ach_dd = env.ref(
            "account_banking_ach_direct_debit.ach_direct_debit",
            raise_if_not_found=False,
        )
        if ach_dd:
            journals.write({"inbound_payment_method_ids": [(4, ach_dd.id)]})
    return
