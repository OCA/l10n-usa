# Copyright (C) 2020 Open Source Integrators
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import base64
import csv
import os
import tempfile

from odoo import api, fields, models
from odoo.tools import misc

import xlsxwriter


class OnPayExport(models.TransientModel):
    _name = "onpay.export"
    _description = "OnPay Export Wizard"

    date_from = fields.Date(string="From")
    date_to = fields.Date(string="To")
    file_type = fields.Selection(
        [("csv", "CSV"), ("xls", "XLS")], default="csv", string="File Type"
    )

    @api.multi
    def export_data(self):
        if self.file_type == "csv":
            res_id, context = self.export_data_csv()
        else:
            res_id, context = self.export_data_xls()
        return {
            "type": "ir.actions.act_window",
            "view_type": "form",
            "view_mode": "form",
            "res_model": "wiz.xls.content",
            "target": "new",
            "res_id": res_id.id,
            "context": context,
        }

    @api.model
    def _get_employee_timesheet_data(self, date_from, date_to):
        """ Timesheet data of employees between selected date """
        self.env.cr.execute(
            """
            SELECT
                opt.code as line_onpay_code,
                he.onpay_code as emp_onpay_code,
                sum(aal.unit_amount) as amount,
                '' as rate,
                opt.treat_as_cash
            FROM account_analytic_line as aal
              INNER JOIN hr_employee he ON he.id = aal.employee_id
              INNER JOIN project_time_type ptt ON ptt.id = aal.time_type_id
                INNER JOIN onpay_pay_type opt ON opt.id = ptt.onpay_pay_type_id
            WHERE aal.employee_id in %s
              AND aal.date >= %s
              AND aal.date <= %s
              AND he.onpay_code IS NOT NULL
              AND opt.code IS NOT NULL
            GROUP BY
                he.onpay_code,
                opt.code,
                opt.treat_as_cash
            """,
            (
                tuple(self.env.context.get("active_ids")),
                date_from,
                date_to,
            ),
        )
        return self.env.cr.dictfetchall()

    @api.model
    def _get_employee_expense_data(self, date_from, date_to):
        """ Expense data (approved) of employees between selected date """
        self.env.cr.execute(
            """
            SELECT
                opt.code as line_onpay_code,
                he.onpay_code as emp_onpay_code,
                sum(exp.total_amount) as amount,
                '' as rate,
                opt.treat_as_cash
            FROM hr_expense exp
              INNER JOIN hr_employee he ON he.id = exp.employee_id
              INNER JOIN product_product pp ON pp.id = exp.product_id
                INNER JOIN product_template pt ON pt.id = pp.product_tmpl_id
                  INNER JOIN onpay_pay_type opt ON opt.id = pt.product_onpay_id
            WHERE exp.employee_id in %s
              AND exp.state IN ('approved', 'done')
              AND exp.payment_mode = 'own_account' /* To Reimburse Employee */
              AND exp.date >= %s
              AND exp.date <= %s
              AND he.onpay_code IS NOT NULL
              AND opt.code IS NOT NULL
            GROUP BY
                he.onpay_code,
                opt.code,
                opt.treat_as_cash
            """,
            (
                tuple(self.env.context.get("active_ids")),
                date_from,
                date_to,
            ),
        )
        return self.env.cr.dictfetchall()

    @api.multi
    def export_data_csv(self):
        if self.env.context.get("active_ids"):
            my_data = self._get_employee_timesheet_data(self.date_from, self.date_to)
            expense_data = self._get_employee_expense_data(self.date_from, self.date_to)

            # XLS sheet creation with header
            file_path = tempfile.mkstemp()
            with open(str(file_path[1]) + ".csv", "w", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(
                    ["type", "id", "emp_num", "hours", "rate", "treat_as_cash"]
                )

                # Write the timesheet data in xls sheet by each employee
                for data in my_data:
                    writer.writerow(
                        [
                            1,
                            data.get("line_onpay_code"),
                            data.get("emp_onpay_code"),
                            data.get("amount"),
                            data.get("rate"),
                            data.get("treat_as_cash") and 1 or 0,
                        ]
                    )

                # Write the data of expense in the xls sheet
                for exp in expense_data:
                    writer.writerow(
                        [
                            1,
                            data.get("line_onpay_code"),
                            data.get("emp_onpay_code"),
                            exp.get("amount"),
                            data.get("rate"),
                            data.get("treat_as_cash") and 1 or 0,
                        ]
                    )

            buf = base64.encodestring(
                open(str(file_path[1]) + ".csv", "rb").read())
            try:
                if buf:
                    os.remove(str(file_path[1]) + ".csv")
            except OSError:
                pass

            cr, uid, context = self.env.args
            context = dict(context)
            context.update({"file": buf})
            self.env.args = cr, uid, misc.frozendict(context)
            res_id = self.env["wiz.xls.content"].create(
                {
                    "file": buf,
                    "name": "OnPay_Data_"
                    + str(self.date_from)
                    + "_"
                    + str(self.date_to)
                    + ".csv",
                }
            )
            return res_id, context

    @api.multi
    def export_data_xls(self):
        if self.env.context.get("active_ids"):
            my_data = self._get_employee_timesheet_data(self.date_from, self.date_to)
            expense_data = self._get_employee_expense_data(self.date_from, self.date_to)

            # XLS sheet creation with header
            file_path = tempfile.mkstemp()
            workbook = xlsxwriter.Workbook(str(file_path[1]) + ".xlsx")
            worksheet = workbook.add_worksheet("OnPay Data")
            worksheet.set_row(0, 15)
            worksheet.set_column(0, 0, 15)
            worksheet.set_column(1, 1, 15)
            worksheet.set_column(2, 2, 15)
            worksheet.set_column(3, 3, 15)
            worksheet.set_column(4, 4, 15)
            worksheet.set_column(5, 5, 15)
            worksheet.write(0, 0, "type")
            worksheet.write(0, 1, "id")
            worksheet.write(0, 2, "emp_num")
            worksheet.write(0, 3, "hours")
            worksheet.write(0, 4, "rate")
            worksheet.write(0, 5, "treat_as_cash")

            row = 1

            # Write the timesheet data in xls sheet by each employee
            for data in my_data:
                worksheet.write(row, 0, "1")
                worksheet.write(row, 1, data.get("line_onpay_code"))
                worksheet.write(row, 2, data.get("emp_onpay_code"))
                worksheet.write(row, 3, data.get("amount"))
                worksheet.write(row, 4, data.get("rate"))
                worksheet.write(row, 5, data.get("treat_as_cash") and 1 or 0)
                row += 1

            # Write the data of expense in the xls sheet
            for exp in expense_data:
                worksheet.write(row, 0, "1")
                worksheet.write(row, 1, data.get("line_onpay_code"))
                worksheet.write(row, 2, data.get("emp_onpay_code"))
                worksheet.write(row, 3, data.get("amount"))
                worksheet.write(row, 4, data.get("rate"))
                worksheet.write(row, 5, data.get("treat_as_cash") and 1 or 0)
                row += 1

            worksheet.freeze_panes(1, 0)
            workbook.close()

            buf = base64.encodestring(
                open(str(file_path[1]) + ".xlsx", "rb").read())
            try:
                if buf:
                    os.remove(str(file_path[1]) + ".xlsx")
            except OSError:
                pass

            cr, uid, context = self.env.args
            context = dict(context)
            context.update({"file": buf})
            self.env.args = cr, uid, misc.frozendict(context)
            res_id = self.env["wiz.xls.content"].create(
                {
                    "file": buf,
                    "name": "OnPay_Data_"
                    + str(self.date_from)
                    + "_"
                    + str(self.date_to)
                    + ".xlsx",
                }
            )
            return res_id, context


class WizOnPayXLSContent(models.TransientModel):

    _name = "wiz.xls.content"
    _description = "XLS/CSV Content"

    @api.model
    def default_get(self, fields):
        # This method is used to get default file name and file content
        res = super(WizOnPayXLSContent, self).default_get(fields)
        # res.update({'name': 'OnPay_Data.xlsx'})
        if self.env.context.get("file"):
            res.update({"file": self.env.context["file"]})
        return res

    file = fields.Binary("File")
    name = fields.Char(string="File Name", size=50)
