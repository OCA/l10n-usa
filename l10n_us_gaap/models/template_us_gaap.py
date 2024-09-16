# ruff: noqa: E501
from odoo import models

from odoo.addons.account.models.chart_template import template


class AccountChartTemplate(models.AbstractModel):
    _inherit = "account.chart.template"

    @template("us_gaap")
    def _get_us_gaap_template_data(self):
        return {
            "name": "US GAAP Chart of Accounts",
            "country": "base.us",
            "code_digits": "6",
        }

    @template("us_gaap", "res.company")
    def _get_us_gaap_res_company(self):
        return {
            self.env.company.id: {
                "anglo_saxon_accounting": True,
                "account_fiscal_country_id": "base.us",
                "bank_account_code_prefix": "1111",
                "cash_account_code_prefix": "1112",
                "transfer_account_code_prefix": "1117",
                "currency_id": "base.USD",
                "property_account_receivable_id": "l10n_us_gaap_account_121",
                "property_account_payable_id": "l10n_us_gaap_account_211",
                "property_account_expense_categ_id": "l10n_us_gaap_account_51202",
                "property_account_income_categ_id": "l10n_us_gaap_account_421",
                "expense_currency_exchange_account_id": "l10n_us_gaap_account_61102",
                "income_currency_exchange_account_id": "l10n_us_gaap_account_61101",
                "account_journal_early_pay_discount_loss_account_id": "l10n_us_gaap_account_41202",
                "account_journal_early_pay_discount_gain_account_id": "l10n_us_gaap_account_42202",
            }
        }
