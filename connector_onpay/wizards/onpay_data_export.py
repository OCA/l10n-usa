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

    @api.multi
    def employee_timesheet_data(self, date_from, date_to):
        # Timesheet data of employees between selected date
        self._cr.execute(
            """select aal.employee_id, aal.line_onpay_id,
                sum(aal.unit_amount) as unit_amount from
                account_analytic_line as aal
                LEFT JOIN hr_employee he ON aal.employee_id = he.id 
                LEFT JOIN project_time_type ptt ON aal.time_type_id = ptt.id
                where he.onpay_code IS NOT Null and
                aal.time_type_id IS NOT Null and
                ptt.onpay_pay_type_id IS NOT Null and
                date >= %s and date <= %s and employee_id in %s group by
                employee_id,line_onpay_id""",
            (
                date_from,
                date_to,
                tuple(self._context.get("active_ids")),
            ),
        )
        return self._cr.dictfetchall()

    @api.multi
    def export_data_csv(self):
        if self._context.get("active_ids"):
            emp_obj = self.env["hr.employee"]
            onpay_type_obj = self.env["onpay.pay.type"]

            my_data = self.employee_timesheet_data(
                self.date_from, self.date_to)

            # Expense data (approved) of employees between selected date
            self._cr.execute(
                """select employee_id,expense_onpay_id,
                sum(total_amount) as
                total_amount from
                hr_expense where date >= %s and
                date <= %s and state='approved' and employee_id in %s
                group by employee_id,expense_onpay_id""",
                (
                    self.date_from,
                    self.date_to,
                    tuple(self._context.get("active_ids")),
                ),
            )
            expense_data = self._cr.dictfetchall()

            # XLS sheet creation with header
            file_path = tempfile.mkstemp()
            with open(str(file_path[1]) + ".csv", "w", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(
                    ["type", "id", "emp_num", "hours", "rate", "treat_as_cash"]
                )

                # Write the timesheet data in xls sheet by each employee
                for data in my_data:
                    emp_id = emp_obj.browse(data.get("employee_id"))
                    on_pay_id = onpay_type_obj.browse(
                        data.get("line_onpay_id"))
                    writer.writerow(
                        [
                            1,
                            on_pay_id.code,
                            emp_id.onpay_code,
                            data.get("unit_amount"),
                            "",
                            on_pay_id.treat_as_cash and 1 or 0,
                        ]
                    )

                # Write the data of expense in the xls sheet
                for exp in expense_data:
                    emp_id_exp = emp_obj.browse(exp.get("employee_id"))
                    onpay_exp_id = onpay_type_obj.browse(
                        exp.get("expense_onpay_id"))
                    writer.writerow(
                        [
                            1,
                            onpay_exp_id.code,
                            emp_id_exp.onpay_code,
                            "",
                            exp.get("total_amount"),
                            onpay_exp_id.treat_as_cash and 1 or 0,
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
        if self._context.get("active_ids"):
            emp_obj = self.env["hr.employee"]
            onpay_type_obj = self.env["onpay.pay.type"]

            my_data = self.employee_timesheet_data(
                self.date_from, self.date_to)

            # Expense data (approved) of employees between selected date
            self._cr.execute(
                """select employee_id,sum(total_amount) as
                total_amount from
                hr_expense where date >= %s and
                date <= %s and state='approved' and employee_id in %s
                group by employee_id""",
                (
                    self.date_from,
                    self.date_to,
                    tuple(self._context.get("active_ids")),
                ),
            )
            expense_data = self._cr.dictfetchall()

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
                emp_id = emp_obj.browse(data.get("employee_id"))
                on_pay_id = onpay_type_obj.browse(data.get("line_onpay_id"))
                worksheet.write(row, 0, "1")
                worksheet.write(row, 1, on_pay_id.code)
                worksheet.write(row, 2, emp_id.onpay_code)
                worksheet.write(row, 3, data.get("unit_amount"))
                worksheet.write(row, 4, "")
                worksheet.write(row, 5, on_pay_id.treat_as_cash and 1 or 0)
                row += 1

            # Find the static onpay type for an expense for now
            onpay_type_id_exp = onpay_type_obj.search([("code", "=", "107")])

            # Write the data of expense in the xls sheet
            for exp in expense_data:
                emp_id_exp = emp_obj.browse(exp.get("employee_id"))
                worksheet.write(row, 0, "1")
                worksheet.write(row, 1, onpay_type_id_exp.code)
                worksheet.write(row, 2, emp_id_exp.onpay_code)
                worksheet.write(row, 3, "")
                worksheet.write(row, 4, exp.get("total_amount"))
                worksheet.write(
                    row, 5, onpay_type_id_exp.treat_as_cash and 1 or 0)
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
        context = self._context
        res = super(WizOnPayXLSContent, self).default_get(fields)
        # res.update({'name': 'OnPay_Data.xlsx'})
        if self._context.get("file"):
            res.update({"file": context["file"]})
        return res

    file = fields.Binary("File")
    name = fields.Char(string="File Name", size=50)
