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
        partners = self.env["res.partner"].search(
            [
                ("autopay", "=", "on_due_date"),
            ]
        )

        self._process_autopay_partners(partners, today)

    @api.model
    def run_autopay_with_invoice_end_of_month(self):
        today = fields.Date.today()
        end_of_month = today + relativedelta(day=31)
        days_to_end_of_month = (end_of_month - today).days

        if days_to_end_of_month != 5:
            _logger.info(
                f"Today is {today}, not 5 days before month end ({end_of_month}), skipping."
            )
            return

        partners = self.env["res.partner"].search(
            [
                ("autopay", "=", "end_of_month"),
            ]
        )

        self._process_autopay_partners(partners, today)

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

    def _process_autopay_partners(self, partners, today):
        plaid_discount_percent = self._get_plaid_discount_percent()

        mail_template = self.env.ref(
            "account_banking_ach_direct_debit_portal.mail_template_autopay_created",
            raise_if_not_found=False,
        )

        for partner in partners:
            invoices = self.env["account.move"].search(
                [
                    ("partner_id", "=", partner.id),
                    ("move_type", "=", "out_invoice"),
                    ("invoice_date_due", "<=", today),
                    ("state", "=", "posted"),
                    ("payment_state", "!=", "paid"),
                ]
            )
            if not invoices:
                continue

            valid_invoices = []
            for invoice in invoices:
                invoice_refs = list(filter(None, [invoice.ref, invoice.name]))

                existing_payment = self.env["account.payment"].search(
                    [
                        ("ref", "in", invoice_refs),
                        ("state", "!=", "cancel"),
                    ],
                    limit=1,
                )

                if not existing_payment:
                    valid_invoices.append(invoice)

            if not valid_invoices:
                continue

            payments_vals = self.make_payment_values(
                valid_invoices, plaid_discount_percent
            )

            if not payments_vals:
                continue

            payment = self.env["account.payment"].create(payments_vals)
            payment.action_post()

            if mail_template and payments_vals:
                currency_obj = self.env["res.currency"].browse(
                    list({val["currency_id"] for val in payments_vals})
                )
                currency_map = {c.id: c for c in currency_obj}

                ctx = {
                    "invoice_lines": [
                        {
                            "name": val["ref"],
                            "amount": val["amount"],
                            "currency": currency_map[val["currency_id"]].name,
                        }
                        for val in payments_vals
                    ],
                    "today": fields.Date.to_string(today),
                }
                mail_template.with_context(**ctx).send_mail(partner.id, force_send=True)

    @api.model
    def make_payment_values(self, invoices, discount_percent):
        payments_vals = []

        payment_date = fields.Date.today()

        for invoice in invoices:
            bank_journal = (
                self.env["account.journal"]
                .sudo()
                .search(
                    [
                        ("company_id", "=", invoice.company_id.id),
                        ("type", "=", "bank"),
                    ],
                    limit=1,
                )
            )

            payment_method_line = bank_journal._get_available_payment_method_lines(
                "inbound"
            ).filtered(lambda l: l.code == "ACH-In")
            if not payment_method_line:
                continue

            amount = invoice.amount_residual
            discount_amount = invoice.currency_id.round(amount * discount_percent / 100)
            amount -= discount_amount

            payments_vals.append(
                {
                    "payment_type": "inbound",
                    "partner_type": "customer",
                    "partner_id": invoice.partner_id.id,
                    "amount": -amount if invoice.move_type == "out_refund" else amount,
                    "currency_id": invoice.currency_id.id,
                    "date": payment_date,
                    "journal_id": bank_journal.id,
                    "payment_method_line_id": payment_method_line.id,
                    "ref": invoice.ref or invoice.name,
                }
            )

        return payments_vals

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
            ]
        )

        partners = invoices.mapped("partner_id")
        for partner in partners:
            partner_invoices = invoices.filtered(lambda inv: inv.partner_id == partner)

            invoice_map = defaultdict(lambda: 0.0)

            for invoice in partner_invoices:
                invoice_refs = list(filter(None, [invoice.ref, invoice.name]))

                existing_payment = self.env["account.payment"].search(
                    [
                        ("ref", "in", invoice_refs),
                        ("state", "!=", "cancel"),
                    ],
                    limit=1,
                )

                if existing_payment:
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
