import logging
from collections import defaultdict
from datetime import timedelta

from dateutil.relativedelta import relativedelta

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
    def run_autopay_with_invoice_on_due_date(self):
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
        today = fields.Date.today()
        end_of_month = today + relativedelta(day=31)
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
    def send_email_autopay_reminders(self):
        today = fields.Date.today()
        end_of_month = today + relativedelta(day=31)
        days_to_end_of_month = (end_of_month - today).days

        self._process_autopay_reminders(today, "on_due_date")

        if days_to_end_of_month == 10:
            self._process_autopay_reminders(today, "end_of_month")

    def _get_plaid_discount_percent(self):
        try:
            plaid_discount = (
                self.env["ir.config_parameter"]
                .sudo()
                .get_param("account_banking_ach_direct_debit_portal.plaid_discount")
            )
            return float(plaid_discount or 0)
        except (TypeError, ValueError, OverflowError):
            return 0

    def _exclude_authorize_invoice_domain(self):
        return [
            "|",
            ("payment_provider_id", "=", False),
            ("payment_provider_id.code", "!=", "authorize"),
        ]

    def _process_autopay_partners(self, partners, date, autopay):
        discount_percent = self._get_plaid_discount_percent()

        mail_template = self.env.ref(
            "account_banking_ach_direct_debit_portal.mail_template_autopay_created",
            raise_if_not_found=False,
        )

        for partner in partners:
            partner_bank = partner.bank_ids.filtered("default")[:1]

            if not partner_bank:
                continue

            invoice_date_due_operator = "="
            if autopay == "end_of_month":
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

            if discount_percent > 0.0:
                # Calculate total discount amount
                total_discount_amount = 0.0
                for invoice in invoices_to_process:
                    amount_residual = (
                        -invoice.amount_residual
                        if invoice.move_type == "out_refund"
                        else invoice.amount_residual
                    )
                    total_discount_amount += amount_residual * discount_percent / 100

                # Round total discount and distribute proportionally
                if total_discount_amount > 0:
                    currency = invoices_to_process[0].currency_id
                    total_discount_amount = currency.round(total_discount_amount)
                    invoices_to_process = self._distribute_discount_amount_autopay(
                        invoices_to_process, total_discount_amount, discount_percent
                    )

            succeeded_invoices = []

            for invoice in invoices_to_process:
                payment_vals = invoice.prepare_payment_register_vals(partner_bank.id)
                register_payment = (
                    self.env["account.payment.register"]
                    .with_context(
                        active_model="account.move",
                        active_ids=[invoice.id],
                    )
                    .sudo()
                    .create(payment_vals)
                )
                is_success = register_payment.with_context(
                    dont_redirect_to_payments=True,
                    force_partner_bank_id=partner_bank.id,
                ).action_create_payments()

                if is_success:
                    invoice.message_post(
                        body=f"Autopay created successfully for invoice <b>{invoice.name}</b>."
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
        plaid_discount_percent = self._get_plaid_discount_percent()

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

                amount = invoice.amount_residual
                discount = invoice.currency_id.round(
                    amount * plaid_discount_percent / 100
                )
                payment_amount = amount - discount
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

    def _distribute_discount_amount_autopay(
        self, invoices_sudo, total_discount_amount, discount_percent
    ):
        if not invoices_sudo or total_discount_amount <= 0:
            return []

        # Calculate base amounts for each invoice
        invoice_amounts = []
        total_base_amount = 0.0

        for invoice in invoices_sudo:
            amount_residual = (
                -invoice.amount_residual
                if invoice.move_type == "out_refund"
                else invoice.amount_residual
            )
            invoice_amounts.append(amount_residual)
            total_base_amount += amount_residual

        # Distribute discount proportionally
        distributed_amount = 0.0
        currency = invoices_sudo[0].currency_id

        succeeded_invoices_sudo = []

        for i, invoice in enumerate(invoices_sudo):
            try:
                if i == len(invoices_sudo) - 1:
                    # Last invoice gets the remainder to ensure total matches exactly
                    invoice_discount = total_discount_amount - distributed_amount
                else:
                    # Calculate proportional amount
                    if total_base_amount > 0:
                        proportion = invoice_amounts[i] / total_base_amount
                        invoice_discount = currency.round(
                            total_discount_amount * proportion
                        )
                    else:
                        invoice_discount = 0.0

                if invoice_discount > 0:
                    invoice.add_discount_line(discount_percent, invoice_discount)

                distributed_amount += invoice_discount
                succeeded_invoices_sudo.append(invoice)
            except Exception as e:
                _logger.warning(
                    f"Add failed discount line for invoice '{invoice.name}': {e}"
                )

        return succeeded_invoices_sudo
