from odoo import api, fields, models


class PaymentToken(models.Model):
    _inherit = "payment.token"

    default = fields.Boolean(default=False)

    @api.model_create_multi
    def create(self, vals_list):
        tokens = super().create(vals_list)
        tokens._enforce_default_payment_token()
        return tokens

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get("skip_default_payment_token"):
            self.with_context(
                skip_default_payment_token=True
            )._enforce_default_payment_token()
        return res

    def unlink(self):
        res = False

        for token in self:
            partner = token.partner_id
            is_default = token.default
            res &= super(PaymentToken, token).unlink()

            if is_default and partner:
                remaining_tokens = self.search(
                    [("partner_id", "=", partner.id)], limit=1
                )
                if remaining_tokens:
                    remaining_tokens.with_context(
                        skip_default_payment_token=True
                    ).write({"default": True})

        return res

    def _enforce_default_payment_token(self):
        for token in self:
            if not token.partner_id:
                continue

            all_tokens = self.search([("partner_id", "=", token.partner_id.id)])
            if len(all_tokens) == 1:
                token.default = True
            elif token.default:
                (all_tokens - token).write({"default": False})
            elif not any(all_tokens.mapped("default")):
                all_tokens[0].default = True
