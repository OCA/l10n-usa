# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import base64
import csv
import io
from datetime import date as date_type

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.l10n_us_sales_tax_engine.levels import (
    LABEL_BY_LEVEL,
    SEQUENCE_BY_LEVEL,
)


class UsTaxReturn(models.Model):
    _name = "us.tax.return"
    _description = "US Sales Tax Return"
    _inherit = ["mail.thread"]
    _order = "date_from desc, state_id"
    _check_company_auto = True

    name = fields.Char(compute="_compute_name", store=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda s: s.env.company,
    )
    currency_id = fields.Many2one(related="company_id.currency_id")
    state_id = fields.Many2one(
        "res.country.state",
        string="State",
        required=True,
        domain=[("country_id.code", "=", "US")],
    )
    period_type = fields.Selection(
        [
            ("monthly", "Monthly"),
            ("quarterly", "Quarterly"),
            ("annual", "Annual"),
            ("custom", "Custom"),
        ],
        default="monthly",
        required=True,
        help="Filing frequency. Used to suggest the period dates; the actual "
        "range is always taken from Period Start / Period End.",
    )
    date_from = fields.Date(string="Period Start", required=True)
    date_to = fields.Date(string="Period End", required=True)
    line_ids = fields.One2many(
        "us.tax.return.line",
        "return_id",
        string="Jurisdiction Lines",
    )
    total_taxable = fields.Monetary(
        compute="_compute_totals", store=True, currency_field="currency_id"
    )
    total_tax = fields.Monetary(
        compute="_compute_totals", store=True, currency_field="currency_id"
    )
    # Gross + exempt sales for the state/period, captured at generation. Stored
    # (not line-derived): exempt sales have no tax line, so they can't be summed
    # from the jurisdiction breakdown. Needed for the SER TotalSales /
    # ExemptionsDeductions header.
    total_sales = fields.Monetary(
        readonly=True, currency_field="currency_id", string="Gross Sales"
    )
    exempt_sales = fields.Monetary(readonly=True, currency_field="currency_id")
    move_count = fields.Integer(compute="_compute_move_count")
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("generated", "Generated"),
            ("filed", "Filed"),
        ],
        string="Status",
        default="draft",
        required=True,
        tracking=True,
    )
    filed_date = fields.Date(readonly=True)
    note = fields.Text()

    @api.depends("state_id", "date_from", "date_to")
    def _compute_name(self):
        for rec in self:
            if rec.state_id and rec.date_from and rec.date_to:
                rec.name = f"{rec.state_id.code} — {rec.date_from} → {rec.date_to}"
            else:
                rec.name = self.env._("New US Tax Return")

    @api.depends("line_ids.taxable_base", "line_ids.tax_amount", "line_ids.level")
    def _compute_totals(self):
        for rec in self:
            # Tax is remitted in full → sum across every jurisdiction line.
            rec.total_tax = sum(rec.line_ids.mapped("tax_amount"))
            # Taxable *sales*, by contrast, must be counted once: the same sale
            # is taxed by state + county + city, so summing line bases would
            # multiply it. The state-level base spans all taxable sales in the
            # state; fall back to the widest level base if no state line exists.
            state_lines = rec.line_ids.filtered(lambda line: line.level == "state")
            if state_lines:
                rec.total_taxable = sum(state_lines.mapped("taxable_base"))
            elif rec.line_ids:
                rec.total_taxable = max(rec.line_ids.mapped("taxable_base"))
            else:
                rec.total_taxable = 0.0

    def _compute_move_count(self):
        for rec in self:
            rec.move_count = len(rec._collect_tax_lines().move_id)

    @api.onchange("period_type", "date_from")
    def _onchange_period(self):
        """Suggest a period end from the start + frequency (editable)."""
        if not self.date_from or self.period_type == "custom":
            return
        start = self.date_from
        if self.period_type == "monthly":
            self.date_to = start + relativedelta(months=1, days=-1)
        elif self.period_type == "quarterly":
            self.date_to = start + relativedelta(months=3, days=-1)
        elif self.period_type == "annual":
            self.date_to = start + relativedelta(years=1, days=-1)

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for rec in self:
            if rec.date_from and rec.date_to and rec.date_from > rec.date_to:
                raise UserError(
                    self.env._("Period Start must be on or before Period End.")
                )

    # ── Source data ───────────────────────────────────────────────────────────

    def _collect_tax_lines(self):
        """Return the posted sale tax move lines this return aggregates.

        Only lines whose tax carries a US jurisdiction tag (``us_tax_level``)
        for this return's state are collected, so non-US-engine taxes booked on
        the same moves are ignored.
        """
        self.ensure_one()
        if not (self.state_id and self.date_from and self.date_to):
            return self.env["account.move.line"]
        return self.env["account.move.line"].search(
            [
                ("company_id", "=", self.company_id.id),
                ("parent_state", "=", "posted"),
                ("move_id.move_type", "in", ("out_invoice", "out_refund")),
                # Tax-point date = invoice_date, matching _gross_sales so the
                # taxable and gross populations can't drift apart.
                ("move_id.invoice_date", ">=", self.date_from),
                ("move_id.invoice_date", "<=", self.date_to),
                ("tax_line_id.us_tax_level", "!=", False),
                ("tax_line_id.us_tax_state_id", "=", self.state_id.id),
            ]
        )

    def _sum_sales_shipped_to_state(self, extra_domain=None):
        """Signed sum of posted customer-sale bases shipped to this return's
        state in the period (refunds net down). Ship-to follows the engine:
        shipping partner else customer. ``extra_domain`` narrows the moves
        (e.g. marketplace-only)."""
        self.ensure_one()
        domain = [
            ("company_id", "=", self.company_id.id),
            ("state", "=", "posted"),
            ("move_type", "in", ("out_invoice", "out_refund")),
            ("invoice_date", ">=", self.date_from),
            ("invoice_date", "<=", self.date_to),
        ] + (extra_domain or [])
        total = 0.0
        for move in self.env["account.move"].search(domain):
            ship = move.partner_shipping_id or move.partner_id
            if ship.state_id != self.state_id:
                continue
            sign = -1.0 if move.move_type == "out_refund" else 1.0
            total += sign * sum(move.invoice_line_ids.mapped("price_subtotal"))
        return total

    def _gross_sales(self):
        """Gross customer sales (incl. exempt) shipped to this state in the
        period — the basis for the SER TotalSales / ExemptionsDeductions."""
        return self._sum_sales_shipped_to_state()

    # ── Actions ─────────────────────────────────────────────────────────────---

    def action_generate(self):
        """(Re)build jurisdiction lines from posted moves in the period."""
        for rec in self:
            rec.line_ids.unlink()
            buckets = {}
            for ml in rec._collect_tax_lines():
                tax = ml.tax_line_id
                key = (tax.us_tax_level, tax.us_tax_jurisdiction_id.id)
                # Sale tax lines are credits (balance < 0); a refund flips both
                # the tax (debit) and the base, so collected tax = -balance and
                # the base is signed by document type.
                sign = -1.0 if ml.move_id.move_type == "out_refund" else 1.0
                bucket = buckets.setdefault(
                    key,
                    {
                        "level": tax.us_tax_level,
                        "jurisdiction_id": tax.us_tax_jurisdiction_id.id,
                        "tax": 0.0,
                        "base": 0.0,
                    },
                )
                bucket["tax"] += -ml.balance
                bucket["base"] += ml.tax_base_amount * sign

            currency = rec.currency_id
            line_vals = []
            for bucket in buckets.values():
                line_vals.append(
                    (
                        0,
                        0,
                        {
                            "sequence": SEQUENCE_BY_LEVEL.get(bucket["level"], 9),
                            "level": bucket["level"],
                            "jurisdiction_id": bucket["jurisdiction_id"],
                            "taxable_base": currency.round(bucket["base"]),
                            "tax_amount": currency.round(bucket["tax"]),
                        },
                    )
                )
            state_base = sum(
                b["base"] for b in buckets.values() if b["level"] == "state"
            )
            if not state_base and buckets:
                state_base = max(b["base"] for b in buckets.values())
            gross = rec._gross_sales()
            # Exempt = gross − taxable; clamp at 0 so a rounding/edge case never
            # emits a negative ExemptionsDeductions (rejected by state portals).
            exempt = max(gross - state_base, 0.0)
            rec.write(
                {
                    "line_ids": line_vals,
                    "state": "generated",
                    "total_sales": currency.round(gross),
                    "exempt_sales": currency.round(exempt),
                }
            )
        return True

    def action_file(self):
        for rec in self:
            if rec.state != "generated":
                raise UserError(
                    self.env._("Generate the return before marking it filed.")
                )
            rec.write({"state": "filed", "filed_date": date_type.today()})
        return True

    def action_reset_to_draft(self):
        self.write({"state": "draft", "filed_date": False})
        return True

    def action_view_moves(self):
        self.ensure_one()
        moves = self._collect_tax_lines().move_id
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Source Invoices"),
            "res_model": "account.move",
            "view_mode": "list,form",
            "domain": [("id", "in", moves.ids)],
        }

    def action_export_worksheet(self):
        """Export the jurisdiction breakdown as a CSV filing worksheet."""
        self.ensure_one()
        if not self.line_ids:
            raise UserError(
                self.env._("Generate the return before exporting a worksheet.")
            )
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "State",
                "Jurisdiction Level",
                "Jurisdiction",
                "FIPS",
                "Taxable Base",
                "Tax Collected",
            ]
        )
        for line in self.line_ids.sorted(lambda r: (r.sequence, r.id)):
            jur = line.jurisdiction_id
            fips = jur.fips_place or jur.fips_county or jur.fips_state or ""
            writer.writerow(
                [
                    self.state_id.code,
                    LABEL_BY_LEVEL.get(line.level, line.level),
                    jur.complete_name or "",
                    fips,
                    f"{line.taxable_base:.2f}",
                    f"{line.tax_amount:.2f}",
                ]
            )
        writer.writerow([])
        writer.writerow(
            ["", "", "TOTAL", "", f"{self.total_taxable:.2f}", f"{self.total_tax:.2f}"]
        )
        filename = (
            f"us_tax_return_{self.state_id.code}_{self.date_from}_{self.date_to}.csv"
        )
        return self._download_attachment(
            filename, buf.getvalue().encode("utf-8"), "text/csv"
        )

    def _download_attachment(self, filename, data_bytes, mimetype):
        """Create an ir.attachment on this return and return a download action."""
        self.ensure_one()
        attachment = self.env["ir.attachment"].create(
            {
                "name": filename,
                "type": "binary",
                "datas": base64.b64encode(data_bytes),
                "res_model": self._name,
                "res_id": self.id,
                "mimetype": mimetype,
            }
        )
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{attachment.id}?download=true",
            "target": "self",
        }
