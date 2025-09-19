from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    surcharge_account_id = fields.Many2one(
        "account.account",
        string="Surcharge Account",
        help="Account to use for credit card surcharges.",
        default=lambda self: self.env.company._get_default_surcharge_discount_account(),
    )
    discount_account_id = fields.Many2one(
        "account.account",
        string="Discount Account",
        default=lambda self: self.env.company._get_default_surcharge_discount_account(),
    )

    discount_journal_id = fields.Many2one(
        "account.journal",
        string="Discount Journal",
        default=lambda self: self.env.company._get_default_discount_journal(),
    )

    def _get_default_surcharge_discount_account(self):
        invoice_journal = self.env["account.journal"].search(
            [("type", "=", "sale"), ("company_id", "=", self.id)], limit=1
        )
        if invoice_journal and invoice_journal.default_account_id:
            return invoice_journal.default_account_id
        return False

    def _get_default_discount_journal(self):
        general_journal = self.env["account.journal"].search(
            [("type", "=", ("general")), ("company_id", "=", self.id)]
        )
        if len(general_journal) > 1:
            general_journal = general_journal.filtered(lambda j: j.code == "MISC")[:1]
            if general_journal:
                return general_journal
        return general_journal[:1] if general_journal else False
