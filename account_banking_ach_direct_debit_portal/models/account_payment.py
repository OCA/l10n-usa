import logging
from calendar import monthrange
from collections import defaultdict
from datetime import date, timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):
    _inherit = "account.payment"

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
        for pay in self:
            pay.available_contact_bank_ids = pay.partner_id.bank_ids.filtered(
                lambda x: x.company_id.id in (False, pay.company_id.id)
            )._origin

    @api.model
    def _specific_date_should_run_today(self, partner, today):
        start = partner.autopay_specific_date
        if not start or today < start:
            return False

        scheduled_day = start.day

        year, month = today.year, today.month
        last_day_of_month = monthrange(year, month)[1]

        run_day_this_month = min(scheduled_day, last_day_of_month)

        return today.day == run_day_this_month

    @api.model
    def _specific_date_next_run_day_this_month(self, partner, any_date):
        start = partner.autopay_specific_date
        if not start:
            return None

        scheduled_day = start.day

        year, month = any_date.year, any_date.month
        last_day_of_month = monthrange(year, month)[1]

        return min(scheduled_day, last_day_of_month)

    @api.model
    def run_autopay_with_invoice_on_due_date(self):
        if (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "account_banking_ach_direct_debit_portal.autopay_enable_on_due_date"
            )
        ) in ["1", "True", "true"]:
            today = fields.Date.today()
            autopay = "on_due_date"

            partners = self.env["res.partner"].search(
                [
                    ("autopay", "=", autopay),
                ]
            )

            self._process_autopay_partners(partners, today, autopay)

    @api.model
    def run_autopay_with_invoice_end_of_month(self):
        if (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "account_banking_ach_direct_debit_portal.autopay_enable_end_of_month"
            )
        ) in ["1", "True", "true"]:
            today = fields.Date.today()

            year, month = today.year, today.month
            last_day = monthrange(year, month)[1]
            end_of_month = date(today.year, today.month, last_day)

            days_to_end_of_month = (end_of_month - today).days

            autopay = "end_of_month"

            if days_to_end_of_month != 5:
                _logger.info(
                    f"Today is {today}, not 5 days before month end ({end_of_month}), skipping."
                )
                return

            partners = self.env["res.partner"].search(
                [
                    ("autopay", "=", autopay),
                ]
            )

            self._process_autopay_partners(partners, today, autopay)

    @api.model
    def run_autopay_with_invoice_specific_date(self):
        if (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "account_banking_ach_direct_debit_portal.autopay_enable_specific_date"
            )
        ) in ["1", "True", "true"]:
            today = fields.Date.today()
            autopay = "specific_date"

            partners = self.env["res.partner"].search(
                [
                    ("autopay", "=", "specific_date"),
                    ("autopay_specific_date", "!=", False),
                ]
            )

            partners_to_run = partners.filtered(
                lambda p: self._specific_date_should_run_today(p, today)
            )

            self._process_autopay_partners(partners_to_run, today, autopay)

    @api.model
    def send_email_autopay_reminders(self):
        today = fields.Date.today()
        year, month = today.year, today.month
        last_day = monthrange(year, month)[1]
        end_of_month = date(today.year, today.month, last_day)
        days_to_end_of_month = (end_of_month - today).days

        if (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "account_banking_ach_direct_debit_portal.autopay_enable_on_due_date"
            )
        ) in ["1", "True", "true"]:
            self._process_autopay_reminders(today, "on_due_date")

        if (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "account_banking_ach_direct_debit_portal.autopay_enable_specific_date"
            )
        ) in ["1", "True", "true"]:
            after_5_days = today + timedelta(days=5)
            partners = self.env["res.partner"].search(
                [
                    ("autopay", "=", "specific_date"),
                    ("autopay_specific_date", "!=", False),
                ]
            )
            partners_due_in_5 = partners.filtered(
                lambda p: self._specific_date_next_run_day_this_month(p, after_5_days)
                == after_5_days.day
                and after_5_days >= p.autopay_specific_date
            )
            if partners_due_in_5:
                self._process_autopay_reminders(today, "specific_date")

        if (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "account_banking_ach_direct_debit_portal.autopay_enable_end_of_month"
            )
        ) in ["1", "True", "true"] and days_to_end_of_month == 10:
            self._process_autopay_reminders(today, "end_of_month")

    def _exclude_authorize_invoice_domain(self):
        return [
            "|",
            ("payment_mode_id", "=", False),
            ("payment_mode_id.payment_method_id.code", "!=", "authorize"),
        ]

    def _process_autopay_partners(self, partners, date, autopay):
        mail_template = self.env.ref(
            "account_banking_ach_direct_debit_portal.mail_template_autopay_created",
            raise_if_not_found=False,
        )

        for partner in partners:
            partner_bank = partner.bank_ids.filtered("default")[:1]

            if not partner_bank:
                _logger.warning(f"Missing Bank Account for: '{partner.name}'")
                continue

            invoice_date_due_operator = "="
            if autopay in ["specific_date", "end_of_month"]:
                invoice_date_due_operator = "<="

            invoices = self.env["account.move"].search(
                [
                    ("partner_id", "=", partner.id),
                    ("move_type", "=", "out_invoice"),
                    ("invoice_date_due", invoice_date_due_operator, date),
                    ("state", "=", "posted"),
                    ("payment_state", "!=", "paid"),
                    ("amount_residual", ">", 0.0),
                    *(self._exclude_authorize_invoice_domain()),
                ]
            )
            invoices_to_process = invoices.filtered(
                lambda i: not i._get_reconciled_payments()
            )
            if not invoices_to_process:
                continue

            today = date.today()

            succeeded_invoices = []
            for invoice in invoices_to_process:
                discount_amount = 0
                charge_amount = 0

                adj_amount, rule = invoice._compute_ach_adjustment(today)

                if rule and rule.discount_or_charge == "discount":
                    discount_amount = adj_amount
                    pay_amount = invoice.amount_residual - discount_amount
                elif rule and rule.discount_or_charge == "charge":
                    charge_amount = adj_amount
                    pay_amount = invoice.amount_residual + charge_amount
                else:
                    pay_amount = invoice.amount_residual

                payment_vals = invoice.prepare_payment_register_vals(partner_bank.id)
                if not payment_vals:
                    continue
                payment_vals.update(
                    {
                        "amount": invoice.currency_id.round(pay_amount),
                    }
                )
                register_payment = (
                    self.env["account.payment.register"]
                    .with_context(
                        active_model="account.move",
                        active_ids=[invoice.id],
                    )
                    .create(payment_vals)
                )

                if rule and charge_amount > 0.0:
                    invoice.add_charge_line(charge_amount, rule)

                is_success = register_payment.with_context(
                    dont_redirect_to_payments=True,
                ).action_create_payments()

                if is_success:
                    invoice.message_post(
                        body=f"Autopay created successfully for invoice <b>{invoice.name}</b>."
                    )
                    if rule and discount_amount > 0.0:
                        invoice._create_discount_entry_and_reconcile(
                            discount_amount, rule
                        )
                    succeeded_invoices.append(invoice)
                else:
                    invoice.message_post(
                        body=f"Autopay failed for invoice <b>{invoice.name}</b>."
                    )

            if mail_template and succeeded_invoices:
                ctx = {
                    "invoice_lines": [
                        {
                            "name": invoice.ref or invoice.name,
                            "amount": invoice.amount_total_signed,
                            "currency": invoice.currency_id.name,
                        }
                        for invoice in succeeded_invoices
                    ],
                    "today": fields.Date.to_string(date),
                }
                mail_template.with_context(**ctx).send_mail(partner.id, force_send=True)

    def _process_autopay_reminders(self, date, autopay):
        invoice_date_due = date + timedelta(days=5)

        mail_template = self.env.ref(
            "account_banking_ach_direct_debit_portal.mail_template_autopay_reminder",
            raise_if_not_found=False,
        )

        invoices = self.env["account.move"].search(
            [
                ("move_type", "=", "out_invoice"),
                ("invoice_date_due", "<=", invoice_date_due),
                ("state", "=", "posted"),
                ("payment_state", "!=", "paid"),
                ("partner_id.autopay", "=", autopay),
                ("amount_residual", ">", 0.0),
                *(self._ach_invoice_domain()),
            ]
        )

        partners = invoices.mapped("partner_id")
        for partner in partners:
            partner_invoices = invoices.filtered(lambda inv: inv.partner_id == partner)

            invoice_map = defaultdict(lambda: 0.0)

            for invoice in partner_invoices:
                if invoice._get_reconciled_payments():
                    continue

                adj_amount, rule = invoice._compute_ach_adjustment(invoice_date_due)

                if rule and rule.discount_or_charge == "discount":
                    discount_amount = adj_amount
                    payment_amount = invoice.amount_residual - discount_amount
                elif rule and rule.discount_or_charge == "charge":
                    charge_amount = adj_amount
                    payment_amount = invoice.amount_residual + charge_amount

                invoice_map[invoice] = payment_amount

            if mail_template and invoice_map:
                ctx = {
                    "invoice_lines": [
                        {
                            "name": inv.name,
                            "amount": amount,
                            "currency": inv.currency_id.name,
                        }
                        for inv, amount in invoice_map.items()
                    ],
                }

                mail_template.with_context(**ctx).send_mail(partner.id, force_send=True)
