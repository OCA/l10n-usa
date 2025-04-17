from odoo import api, fields, models


class ResPartnerBank(models.Model):
    _inherit = "res.partner.bank"

    bank_address = fields.Char(related="bank_id.street", readonly=False)
    verified = fields.Boolean(default=False)
    default = fields.Boolean(default=False)
    plaid_access_token = fields.Char(readonly=True)
    plaid_account_id = fields.Char(readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        banks = super().create(vals_list)
        banks._enforce_default_bank_constraint()
        return banks

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get("skip_default_bank_constraint"):
            self.with_context(
                skip_default_bank_constraint=True
            )._enforce_default_bank_constraint()
        return res

    def unlink(self):
        res = False

        for bank in self:
            partner = bank.partner_id
            is_default = bank.default
            res &= super(ResPartnerBank, bank).unlink()

            if is_default and partner:
                remaining_banks = self.search(
                    [("partner_id", "=", partner.id)], limit=1
                )
                if remaining_banks:
                    remaining_banks.with_context(
                        skip_default_bank_constraint=True
                    ).write({"default": True})

        return res

    def _enforce_default_bank_constraint(self):
        for bank in self:
            if not bank.partner_id:
                continue

            all_banks = self.search([("partner_id", "=", bank.partner_id.id)])
            if len(all_banks) == 1:
                all_banks.default = True
            elif bank.default:
                (all_banks - bank).write({"default": False})
            elif not any(all_banks.mapped("default")):
                all_banks[0].default = True
