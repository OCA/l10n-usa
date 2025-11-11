from datetime import datetime, timedelta

from odoo import fields, models


class AccountPaymentTerm(models.Model):
    _inherit = "account.payment.term"

    ach_rule_ids = fields.One2many(
        "ach.payment.discount.rule",
        "payment_term_id",
        string="ACH Payment Discount Rules",
    )

    def _get_ach_rule_base_date(self, rule, invoice):
        if rule.based_on == "ship_date":
            sale_orders = invoice.invoice_line_ids.mapped(
                "sale_line_ids.order_id"
            ).filtered(lambda so: so.commitment_date)
            if not sale_orders:
                return None

            earliest_order = min(sale_orders, key=lambda so: so.commitment_date)
            return earliest_order.commitment_date

        elif rule.based_on == "due_date":
            return invoice.invoice_date_due

    def _get_applicable_ach_rule(self, invoice, pay_date):
        self.ensure_one()

        if isinstance(pay_date, datetime):
            pay_date = pay_date.date()

        rules = self.ach_rule_ids

        def _normalize_base_date(rule):
            base_date = self._get_ach_rule_base_date(rule, invoice)
            if not base_date:
                return None
            if isinstance(base_date, datetime):
                base_date = base_date.date()
            return base_date

        before_rules = rules.filtered(lambda r: r.before_or_after == "before").sorted(
            key=lambda r: (r.sequence, r.id)
        )

        for rule in before_rules:
            base_date = _normalize_base_date(rule)
            if not base_date:
                continue

            limit_date = base_date - timedelta(days=rule.no_days or 0)
            if pay_date <= limit_date:
                return rule

        after_rules = rules.filtered(lambda r: r.before_or_after == "after").sorted(
            key=lambda r: (r.sequence, r.id), reverse=True
        )

        for rule in after_rules:
            base_date = _normalize_base_date(rule)
            if not base_date:
                continue

            limit_date = base_date + timedelta(days=rule.no_days or 0)
            if pay_date >= limit_date:
                return rule

        return False
