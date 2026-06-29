# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models


class MisReportInstance(models.Model):
    _inherit = "mis.report.instance"

    hide_all_lines_0 = fields.Boolean(
        string="Hide line value 0",
        help="Hide empty lines or lines with value 0.",
        default=True,
    )

    journal_ids = fields.Many2many(comodel_name="account.journal", string="Journals")

    def _get_filter_domain(self, source_aml_model_name):
        domain = super()._get_filter_domain(source_aml_model_name)
        if self.journal_ids:
            domain += [("journal_id", "in", self.journal_ids.ids)]
        return domain

    def hide_all_lines(self):
        report_styles = set(
            self.report_id.mapped("kpi_ids.style_id")
            + self.report_id.mapped("kpi_ids.auto_expand_accounts_style_id")
        )
        for style in report_styles:
            style.hide_empty = self.hide_all_lines_0
            style.hide_empty_inherit = self.hide_all_lines_0
            style.hide_always = False
            style.hide_always_inherit = False

    def write(self, vals):
        res = super().write(vals)
        if "hide_all_lines_0" in vals:
            self.hide_all_lines()
        return res

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        for report in res:
            report.hide_all_lines()
        return res
