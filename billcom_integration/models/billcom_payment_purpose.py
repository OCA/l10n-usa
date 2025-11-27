import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class BillcomPaymentPurpose(models.Model):
    _name = "billcom.payment.purpose"
    _description = "Bill.com Payment Purpose"
    _order = "country_id, code"

    name = fields.Char(compute="_compute_get_name", store=True)
    code = fields.Char(required=True)
    description = fields.Char()
    active = fields.Boolean(default=True)
    country_id = fields.Many2one(
        "res.country",
        required=True,
        default=lambda self: self.env.ref("base.us", raise_if_not_found=False),
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Bill Currency",
        help="Currency used for bills to vendors in this country",
    )
    account_type = fields.Selection(
        [
            ("NONE", "None"),
            ("CHECKING", "Checking"),
            ("SAVINGS", "Savings"),
        ],
        default="NONE",
        help="Bank account type for international payments",
    )
    billcom_data = fields.Text(
        "Bill.com Raw Data", help="Raw JSON data from Bill.com API for reference"
    )

    _sql_constraints = [
        (
            "unique_payment_purpose",
            "unique(country_id, currency_id, account_type, code)",
            "Payment purpose must be unique per country, currency, account type and code!",
        )
    ]

    @api.depends("code", "description")
    def _compute_get_name(self):
        for record in self:
            record.name = f"{record.code} - \
            {record.description[:50] if record.description else ''}"

    @api.model
    def fetch_payment_purposes_for_config(
        self, country_id, currency_id, account_type="NONE"
    ):
        country = self.env["res.country"].browse(country_id)
        currency = self.env["res.currency"].browse(currency_id)

        if not country or not currency:
            raise UserError(_("Invalid country or currency"))

        # Don't fetch for US vendors
        if country.code == "US":
            raise UserError(
                _(
                    "Payment purposes are only required for "
                    "international (non-US) vendors"
                )
            )

        service = self.env["billcom.service"]

        try:
            # Build API endpoint with query parameters
            params = {
                "country": country.code,
                "billCurrency": currency.name,
                "accountType": account_type,
            }

            _logger.info(
                "Fetching payment purposes from Bill.com for "
                "country=%s, currency=%s, accountType=%s",
                country.code,
                currency.name,
                account_type,
            )

            response = service._make_request(
                "vendors/configuration/international-payments",
                method="GET",
                params=params,
            )

            if not response:
                raise UserError(_("No response from Bill.com API"))

            international_payments = response.get("internationalPayments", {})
            payment_purpose_config = international_payments.get("paymentPurpose", {})

            if not payment_purpose_config:
                _logger.warning(
                    f"No payment purpose configuration returned for "
                    f"country={country.code}, "
                    f"currency={currency.name}, accountType={account_type}"
                )
                return self.env["billcom.payment.purpose"]

            # Get payment purpose type and codes
            purpose_required = payment_purpose_config.get("required", False)
            purpose_type = payment_purpose_config.get("type", "CODE")  # CODE or TEXT
            purpose_codes = payment_purpose_config.get("codes", [])

            _logger.info(
                "Payment purpose config: required=%s, type=%s, " "codes_count=%s",
                purpose_required,
                purpose_type,
                len(purpose_codes) if isinstance(purpose_codes, list) else 0,
            )

            # If type is TEXT, there are no predefined codes
            if purpose_type == "TEXT" or not purpose_codes:
                _logger.info(
                    f"Payment purpose type is TEXT or no codes available for "
                    f"country={country.code}. "
                    f"User must enter free text."
                )
                return self.env["billcom.payment.purpose"]

            # Process payment purpose codes
            created_records = self.env["billcom.payment.purpose"]

            for purpose_data in purpose_codes:
                purpose_code = purpose_data.get("value")
                purpose_desc = purpose_data.get("name", "")

                if not purpose_code:
                    _logger.warning(
                        f"Skipping payment purpose without value: {purpose_data}"
                    )
                    continue

                # Check if record already exists
                existing = self.search(
                    [
                        ("country_id", "=", country.id),
                        ("currency_id", "=", currency.id),
                        ("account_type", "=", account_type),
                        ("code", "=", purpose_code),
                    ],
                    limit=1,
                )

                vals = {
                    "code": purpose_code,
                    "description": purpose_desc,
                    "country_id": country.id,
                    "currency_id": currency.id,
                    "account_type": account_type,
                    "billcom_data": str(payment_purpose_config),
                    "active": True,
                }

                if existing:
                    # Update existing record
                    existing.write(vals)
                    created_records |= existing
                    _logger.info(
                        "Updated payment purpose: %s - %s",
                        purpose_code,
                        purpose_desc,
                    )
                else:
                    # Create new record
                    new_record = self.create(vals)
                    created_records |= new_record
                    _logger.info(
                        f"Created payment purpose: {purpose_code} - {purpose_desc}"
                    )

            return created_records

        except Exception as e:
            _logger.error(f"Error fetching payment purposes from Bill.com: {e}")
            raise UserError(
                _("Error fetching payment purposes from Bill.com: %s") % str(e)
            ) from e
