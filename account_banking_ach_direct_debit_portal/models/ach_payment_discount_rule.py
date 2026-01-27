import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class AchPaymentDiscountRule(models.Model):
    _name = "ach.payment.discount.rule"

    payment_term_id = fields.Many2one(
        "account.payment.term",
        string="Payment Term",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(default=10)
    before_or_after = fields.Selection(
        selection=[
            ("before", "Before"),
            ("after", "After"),
        ],
        string="Before / After",
        required=True,
        default="before",
    )
    no_days = fields.Integer("No. Days")
    based_on = fields.Selection(
        selection=[
            ("ship_date", "Ship Date"),
            ("due_date", "Due Date"),
        ],
        required=True,
        default="ship_date",
    )
    discount_or_charge = fields.Selection(
        [
            ("discount", "Discount"),
            ("charge", "Charge"),
        ],
        string="Discount or Charge",
        required=True,
        default="discount",
    )
    amount_type = fields.Selection(
        [
            ("percent", "Percentage"),
            ("fixed", "Amount"),
        ],
        required=True,
        default="percent",
    )
    amount = fields.Float(
        required=True,
        help="If percentage, enter percent (e.g. 1 = 1%). If fixed, enter currency amount.",
    )
