# Copyright 2025 Binhex - Simple Solutions
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class BillcomSyncWizard(models.TransientModel):
    _name = "billcom.sync.wizard"
    _description = "Bill.com Synchronization Wizard"

    # Sync Options
    sync_vendors = fields.Boolean(
        default=True,
        help="Synchronize vendor/supplier data with Bill.com",
    )
    sync_customers = fields.Boolean(
        default=False,
        help="Synchronize customer data with Bill.com",
    )
    sync_bills = fields.Boolean(
        string="Sync Vendor Bills",
        default=True,
        help="Synchronize vendor bills/invoices with Bill.com",
    )
    sync_invoices = fields.Boolean(
        string="Sync Customer Invoices",
        default=False,
        help="Synchronize customer invoices with Bill.com",
    )
    sync_payments = fields.Boolean(
        default=True,
        help="Synchronize payment data with Bill.com",
    )
    sync_documents = fields.Boolean(
        default=False,
        help="Synchronize bill documents with Bill.com",
    )

    # Sync Direction
    sync_direction = fields.Selection(
        [
            ("odoo_to_billcom", "Odoo → Bill.com"),
            ("billcom_to_odoo", "Bill.com → Odoo"),
            ("bidirectional", "Bidirectional"),
        ],
        default="billcom_to_odoo",
        required=True,
    )

    # Filtering Options
    filter_by_date = fields.Boolean(
        default=True,
        help="Only sync records within the specified date range \
            (Recommended for API performance)",
    )
    date_from = fields.Date(
        default=lambda self: fields.Date.today() - timedelta(days=30),
        help="Start date for filtering records (default: last 30 days)",
    )
    date_to = fields.Date(
        default=fields.Date.today,
        help="End date for filtering records (default: today)",
    )

    filter_by_partner = fields.Boolean(
        default=False, help="Only sync specific partners"
    )
    partner_ids = fields.Many2many(
        "res.partner",
        domain=["|", ("supplier_rank", ">", 0), ("customer_rank", ">", 0)],
    )

    only_billcom_enabled = fields.Boolean(
        string="Only Bill.com Enabled Records",
        default=True,
        help="Only sync records marked for Bill.com synchronization",
    )

    # Advanced Filters (Bill.com API v3 specific)
    # Vendor/Customer Filters
    filter_vendor_account_type = fields.Selection(
        [
            ("BUSINESS", "Business"),
            ("PERSON", "Person"),
        ],
        string="Vendor Account Type",
        help="Filter vendors by account type",
    )
    filter_vendor_currency = fields.Many2one(
        "res.currency",
        string="Vendor Currency",
        help="Filter vendors by bill currency (e.g., USD, CAD)",
    )
    filter_customer_account_type = fields.Selection(
        [
            ("BUSINESS", "Business"),
            ("PERSON", "Person"),
        ],
        string="Customer Account Type",
        help="Filter customers by account type",
    )

    # Bill/Invoice Filters - Allow multiple selections
    filter_bill_status = fields.Many2many(
        comodel_name="billcom.bill.status",
        relation="billcom_wizard_bill_status_rel",
        column1="wizard_id",
        column2="status_id",
        string="Bill Payment Status",
        help="Filter bills by payment status (leave empty for all statuses)",
    )
    filter_bill_approval_status = fields.Many2many(
        comodel_name="billcom.bill.approval.status",
        relation="billcom_wizard_bill_approval_status_rel",
        column1="wizard_id",
        column2="status_id",
        string="Bill Approval Status",
        help="Filter bills by approval status (leave empty for all statuses)",
    )
    filter_invoice_status = fields.Many2many(
        comodel_name="billcom.invoice.status",
        relation="billcom_wizard_invoice_status_rel",
        column1="wizard_id",
        column2="status_id",
        string="Invoice Status",
        help="Filter invoices by status (leave empty for all statuses)",
    )

    # Payment Filters - Allow multiple selections
    filter_payment_status = fields.Many2many(
        comodel_name="billcom.payment.status",
        relation="billcom_wizard_payment_status_rel",
        column1="wizard_id",
        column2="status_id",
        string="Payment Status",
        help="Filter payments by status (leave empty for all statuses)",
    )

    # Processing Options
    process_immediately = fields.Boolean(
        default=True,
        help="Process sync items immediately instead of queuing them",
    )
    batch_size = fields.Integer(
        default=50,
        help="Number of records to process in each batch",
    )

    # Priority
    priority = fields.Selection(
        [
            ("0", "Low"),
            ("1", "Normal"),
            ("2", "High"),
            ("3", "Critical"),
        ],
        default="1",
    )

    # Results
    result_summary = fields.Html(readonly=True, sanitize=False)

    @api.onchange("filter_by_date")
    def _onchange_filter_by_date(self):
        """Date filters are recommended for API performance, so we keep default values"""
        if self.filter_by_date and not self.date_from:
            self.date_from = fields.Date.today() - timedelta(days=30)
        if self.filter_by_date and not self.date_to:
            self.date_to = fields.Date.today()

    @api.onchange("filter_by_partner")
    def _onchange_filter_by_partner(self):
        if not self.filter_by_partner:
            self.partner_ids = [(5, 0, 0)]

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        """Validate that date_from is before date_to"""
        for record in self:
            if record.date_from and record.date_to:
                if record.date_from > record.date_to:
                    raise UserError(_("'From Date' must be earlier than 'To Date'"))

    def action_start_sync(self):
        """Start the synchronization process"""
        self.ensure_one()

        # Validate configuration
        config = self.env["billcom.config"].sudo().get_config()
        if not config:
            raise UserError(_("No active Bill.com configuration found"))

        # Check if at least one sync type is selected
        sync_types = []
        if self.sync_vendors:
            sync_types.append("vendor")
        if self.sync_customers:
            sync_types.append("customer")
        if self.sync_bills:
            sync_types.append("bill")
        if self.sync_invoices:
            sync_types.append("invoice")
        if self.sync_payments:
            sync_types.append("payment")
        if self.sync_documents:
            sync_types.append("document")

        if not sync_types:
            raise UserError(_("Please select at least one sync type"))

        # Create sync queue items
        queue_items = []
        sync_stats = {}

        for sync_type in sync_types:
            try:
                items = self._create_sync_items(sync_type)
                queue_items.extend(items)
                sync_stats[sync_type] = {"items": len(items), "error": None}
            except Exception as e:
                _logger.error(f"Error creating sync items for {sync_type}: {e}")
                sync_stats[sync_type] = {"items": 0, "error": str(e)}

        total_items = len(queue_items)

        if not queue_items:
            raise UserError(_("No records found matching the specified criteria"))

        # Process immediately or queue for later
        processed_results = None
        if self.process_immediately:
            processed_results = self._process_sync_items(queue_items)

        # Generate HTML summary with improved UI
        self.result_summary = self._generate_html_summary(
            sync_stats, total_items, processed_results
        )

        # Return action to show results
        return {
            "type": "ir.actions.act_window",
            "name": "Sync Results",
            "res_model": "billcom.sync.wizard",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
            "context": {"show_results": True},
        }

    def _generate_html_summary(
        self, sync_stats, total_items, processed_results=None
    ):  # noqa: C901,E501,B950
        """Generate an HTML summary with improved visual design"""
        # flake8: noqa

        # Icon mapping for sync types
        type_icons = {
            "vendor": "👥",
            "customer": "🛒",
            "bill": "📄",
            "invoice": "📑",
            "payment": "💰",
            "document": "📎",
        }

        # Color mapping for sync types
        type_colors = {
            "vendor": "#875A7B",
            "customer": "#00A09D",
            "bill": "#F06050",
            "invoice": "#00A09D",
            "payment": "#17A2B8",
            "document": "#6C757D",
        }

        html = """
        <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        max-width: 800px; margin: 0 auto;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 25px; border-radius: 10px 10px 0 0; color: white;">
                <h2 style="margin: 0; font-size: 24px; font-weight: 600;">
                    <span style="font-size: 28px;">📊</span> Synchronization Results
                </h2>
            </div>
        """

        # Sync items summary
        html += '<div style="background: white; padding: 20px; border-left: 3px \
             solid #e0e0e0; border-right: 3px solid #e0e0e0;">'
        html += '<h3 style="color: #333; margin-top: 0; border-bottom: 2px \
         solid #f0f0f0; padding-bottom: 10px;">📋 Items to Sync</h3>'
        html += '<div style="display: grid; grid-template-columns: \
             repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-top: 15px;">'

        for sync_type, stats in sync_stats.items():
            icon = type_icons.get(sync_type, "📦")
            color = type_colors.get(sync_type, "#6C757D")

            if stats["error"]:
                # Error card
                html += f"""
                <div style="background: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);">
                    <div style="font-size: 24px; margin-bottom: 5px;">{icon}</div>
                    <div style="font-weight: 600; color: #333; text-transform: capitalize;">{sync_type}</div>
                    <div style="color: #856404; font-size: 12px; margin-top: 5px;">⚠️ Error</div>
                    <div style="font-size: 11px; color: #666; margin-top: 5px; word-break: break-word;">{stats['error'][:50]}...</div>
                </div>
                """  # noqa: E231,E501
            else:
                # Success card
                html += f"""
                <div style="background: white; border-left: 4px solid {color}; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);">
                    <div style="font-size: 24px; margin-bottom: 5px;">{icon}</div>
                    <div style="font-weight: 600; color: #333; text-transform: capitalize;">{sync_type}</div>
                    <div style="font-size: 28px; font-weight: bold; color: {color}; margin-top: 5px;">{stats['items']}</div>
                    <div style="font-size: 12px; color: #999;">items</div>
                </div>
                """  # noqa: E231,E501

        html += "</div></div>"

        # Processing results (if processed immediately)
        if processed_results:
            success_count = processed_results["processed"]
            error_count = processed_results["errors"]
            total = processed_results["total"]
            success_rate = (success_count / total * 100) if total > 0 else 0

            html += '<div style="background: white; padding: 20px; border-left: 3px \
                 solid #e0e0e0; border-right: 3px solid #e0e0e0; border-top: 1px solid #f0f0f0;">'
            html += '<h3 style="color: #333; margin-top: 0; border-bottom: 2px \
             solid #f0f0f0; padding-bottom: 10px;">⚡ Processing Results</h3>'

            # Summary cards
            html += '<div style="display: grid; grid-template-columns: repeat(3, 1fr); \
                 gap: 15px; margin-bottom: 20px;">'

            # Success card
            html += f"""
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; border-radius: 8px; color: white; text-align: center;">
                <div style="font-size: 14px; opacity: 0.9; margin-bottom: 5px;">Total Items</div>
                <div style="font-size: 36px; font-weight: bold;">{total}</div>
            </div>
            """  # noqa: E231,E501

            # Success count card
            html += f"""
            <div style="background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); padding: 20px; border-radius: 8px; color: white; text-align: center;">
                <div style="font-size: 14px; opacity: 0.9; margin-bottom: 5px;">✓ Successful</div>
                <div style="font-size: 36px; font-weight: bold;">{success_count}</div>
            </div>
            """  # noqa: E231,E501

            # Error count card
            html += f"""
            <div style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); padding: 20px; border-radius: 8px; color: white; text-align: center;">
                <div style="font-size: 14px; opacity: 0.9; margin-bottom: 5px;">✗ Errors</div>
                <div style="font-size: 36px; font-weight: bold;">{error_count}</div>
            </div>
            """  # noqa: E231,E501,B950

            html += "</div>"

            # Progress bar
            html += f"""
            <div style="margin-top: 20px;">
                <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                    <span style="font-weight: 600; color: #333;">Success Rate</span>
                    <span style="font-weight: 600; color: #11998e;">{success_rate:.1f}%</span>
                </div>
                <div style="background: #e0e0e0; border-radius: 10px; height: 20px; overflow: hidden;">
                    <div style="background: linear-gradient(90deg, #11998e 0%, #38ef7d 100%); height: 100%; width: {success_rate}%; transition: width 0.3s ease;"></div>
                </div>
            </div>
            """  # noqa: E231,E501,B950

            html += "</div>"
        else:
            # Queued message
            html += f"""
            <div style="background: white; padding: 20px; border-left: 3px solid #e0e0e0; border-right: 3px solid #e0e0e0; border-top: 1px solid #f0f0f0;">
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; border-radius: 8px; color: white; text-align: center;">
                    <div style="font-size: 48px; margin-bottom: 10px;">⏳</div>
                    <h3 style="margin: 0 0 10px 0;">Items Queued for Processing</h3>
                    <div style="font-size: 32px; font-weight: bold; margin: 10px 0;">{total_items}</div>
                    <div style="font-size: 14px; opacity: 0.9;">Items will be processed by the scheduled action</div>
                </div>
            </div>
            """  # noqa: E231,E501,B950

        # Footer
        html += """
            <div style="background: #f8f9fa; padding: 15px 20px; border-radius: 0 0 10px 10px; border: 3px solid #e0e0e0; border-top: none; text-align: center; color: #6c757d; font-size: 12px;">
                <span style="font-size: 14px;">💡</span> Use the buttons below to view the sync queue or logs for more details
            </div>
        </div>
        """  # noqa: E231,E501,B950

        return html

    def _create_sync_items(self, sync_type):
        """Create sync queue items for a specific type"""
        # Check sync direction - if from BILL to Odoo, fetch from API first
        if self.sync_direction in ["billcom_to_odoo", "bidirectional"]:
            return self._create_sync_items_from_billcom(sync_type)
        else:
            # Odoo to BILL - find records in Odoo
            if sync_type == "vendor":
                return self._create_partner_sync_items("vendor")
            elif sync_type == "customer":
                return self._create_partner_sync_items("customer")
            elif sync_type == "bill":
                return self._create_bill_sync_items()
            elif sync_type == "invoice":
                return self._create_invoice_sync_items()
            elif sync_type == "payment":
                return self._create_payment_sync_items()
            elif sync_type == "document":
                return self._create_document_sync_items()
            else:
                return []

    def _create_sync_items_from_billcom(self, sync_type):
        service = self.env["billcom.service"]
        config = self.env["billcom.config"].sudo().get_config()

        if not config:
            raise UserError(_("No active Bill.com configuration found"))

        queue_items = []

        try:
            if sync_type == "vendor":
                queue_items = self._fetch_vendors_from_billcom(service, config)
            elif sync_type == "customer":
                queue_items = self._fetch_customers_from_billcom(service, config)
            elif sync_type == "bill":
                queue_items = self._fetch_bills_from_billcom(service, config)
            elif sync_type == "invoice":
                queue_items = self._fetch_invoices_from_billcom(service, config)
            elif sync_type == "payment":
                queue_items = self._fetch_payments_from_billcom(service, config)
            else:
                _logger.warning(f"Sync from BILL not supported for type: {sync_type}")

            _logger.info(f"Fetched {len(queue_items)} {sync_type} items from BILL.com")

        except Exception as e:
            _logger.exception(f"Error fetching {sync_type} from BILL: {e}")
            raise UserError(
                _(f"Failed to fetch {sync_type} from Bill.com: {str(e)}")
            ) from e

        return queue_items

    def _build_billcom_filters(self, sync_type):  # noqa: C901
        """Build Bill.com API v3 filters string

        Format: filters=field1:op:value,field2:op:value
        Example: filters=archived:eq:false,createdTime:gte:2025-01-01T00:00:00.000Z

        Args:
            sync_type: vendor, customer, bill, invoice, or payment

        Returns:
            dict: Query parameters with filters
        """
        filters = []
        params = {}

        if sync_type in ["vendor", "customer"]:
            filters.append("archived:eq:false")

        if self.filter_by_date:
            if self.date_from:
                from_datetime = (
                    f"{self.date_from.isoformat()}T00:00:00.000Z"  # noqa: E231
                )
                filters.append(f"createdTime:gte:{from_datetime}")
            if self.date_to:
                to_datetime = f"{self.date_to.isoformat()}T23:59:59.999Z"  # noqa: E231
                filters.append(f"createdTime:lte:{to_datetime}")

        # Partner filter by Bill.com vendor/customer IDs
        if self.filter_by_partner and self.partner_ids:
            billcom_ids = self.partner_ids.filtered(lambda p: p.billcom_id).mapped(
                "billcom_id"
            )
            if billcom_ids:
                if sync_type == "vendor":
                    id_field = "id"
                elif sync_type == "customer":
                    id_field = "id"
                elif sync_type == "bill":
                    id_field = "vendorId"
                elif sync_type == "invoice":
                    id_field = "customerId"
                elif sync_type == "payment":
                    id_field = "vendorId"
                else:
                    id_field = "id"

                if len(billcom_ids) == 1:
                    filters.append(f"{id_field}: eq: {billcom_ids[0]}")
                else:
                    ids_str = ",".join(billcom_ids)
                    filters.append(f"{id_field}: in: ({ids_str})")

        # Sync-type specific filters
        if sync_type == "vendor":
            if self.filter_vendor_account_type:
                filters.append(f"accountType: eq: {self.filter_vendor_account_type}")
            if self.filter_vendor_currency:
                filters.append(f"billCurrency: eq: {self.filter_vendor_currency.name}")

        elif sync_type == "customer":
            if self.filter_customer_account_type:
                filters.append(f"accountType: eq: {self.filter_customer_account_type}")

        elif sync_type == "bill":
            if self.filter_bill_status:
                status_codes = self.filter_bill_status.mapped("code")
                if len(status_codes) == 1:
                    filters.append(f"paymentStatus: eq: {status_codes[0]}")
                else:
                    status_str = ",".join(status_codes)
                    filters.append(f"paymentStatus: in: ({status_str})")

            if self.filter_bill_approval_status:
                approval_codes = self.filter_bill_approval_status.mapped("code")
                if len(approval_codes) == 1:
                    filters.append(f"approvalStatus: eq: {approval_codes[0]}")
                else:
                    approval_str = ",".join(approval_codes)
                    filters.append(f"approvalStatus: in: ({approval_str})")

        elif sync_type == "invoice":
            if self.filter_invoice_status:
                status_codes = self.filter_invoice_status.mapped("code")
                if len(status_codes) == 1:
                    filters.append(f"status: eq: {status_codes[0]}")
                else:
                    status_str = ",".join(status_codes)
                    filters.append(f"status: in: ({status_str})")

        elif sync_type == "payment":
            if self.filter_payment_status:
                status_codes = self.filter_payment_status.mapped("code")
                if len(status_codes) == 1:
                    filters.append(f"status: eq: {status_codes[0]}")
                else:
                    status_str = ",".join(status_codes)
                    filters.append(f"status: in: ({status_str})")

        if filters:
            params["filters"] = ",".join(filters)

        return params

    def _fetch_vendors_from_billcom(self, service, config):
        queue_items = []

        params = self._build_billcom_filters("vendor")
        endpoint = "vendors"

        _logger.info(f"Calling BILL API endpoint: {endpoint} with params: {params}")

        response = service._make_request(endpoint, method="GET", params=params)
        vendors_data = response.get("results", [])

        if not vendors_data and response.get("status") == "error":
            raise UserError(
                _(f"BILL API error: {response.get('errorMessage', 'Unknown error')}")
            )

        _logger.info(
            f"Fetched {len(vendors_data)} vendors from BILL "
            f"with filters: {params.get('filters', 'none')}"
        )

        for vendor_data in vendors_data:
            billcom_vendor_id = vendor_data.get("id")

            partner = self.env["res.partner"].search(
                [("billcom_id", "=", billcom_vendor_id)], limit=1
            )

            queue_item = self.env["billcom.sync.queue"].create(
                {
                    "sync_type": "vendor",
                    "record_model": "res.partner",
                    "record_id": partner.id if partner else None,
                    "direction": self.sync_direction,
                    "operation": "update" if partner else "create",
                    "priority": self.priority,
                    "state": "queued",
                    "billcom_id": billcom_vendor_id,
                    "sync_data": str(vendor_data),  # Store BILL data for processing
                }
            )
            queue_items.append(queue_item)

        return queue_items

    def _fetch_customers_from_billcom(self, service, config):
        """Fetch customers from BILL API and create queue items"""
        queue_items = []

        # Build API filters using BILL API v3 format
        params = self._build_billcom_filters("customer")
        endpoint = "customers"

        _logger.info(f"Calling BILL API endpoint: {endpoint} with params: {params}")

        # Call BILL API with params dictionary
        response = service._make_request(endpoint, method="GET", params=params)

        # BILL API v3 returns data in 'results' array
        customers_data = response.get("results", [])

        if not customers_data and response.get("status") == "error":
            raise UserError(
                _(f"BILL API error: {response.get('errorMessage', 'Unknown error')}")
            )

        _logger.info(
            f"Fetched {len(customers_data)} customers from BILL "
            f"with filters: {params.get('filters', 'none')}"
        )

        for customer_data in customers_data:
            billcom_customer_id = customer_data.get("id")

            partner = self.env["res.partner"].search(
                [("billcom_id", "=", billcom_customer_id)], limit=1
            )

            queue_item = self.env["billcom.sync.queue"].create(
                {
                    "sync_type": "customer",
                    "record_model": "res.partner",
                    "record_id": partner.id if partner else None,
                    "direction": self.sync_direction,
                    "operation": "update" if partner else "create",
                    "priority": self.priority,
                    "state": "queued",
                    "billcom_id": billcom_customer_id,
                    "sync_data": str(customer_data),
                }
            )
            queue_items.append(queue_item)

        return queue_items

    def _fetch_bills_from_billcom(self, service, config):
        """Fetch bills from BILL API and create queue items"""
        queue_items = []

        # Build API filters using BILL API v3 format
        params = self._build_billcom_filters("bill")
        endpoint = "bills"

        _logger.info(f"Calling BILL API endpoint: {endpoint} with params: {params}")

        # Call BILL API with params dictionary
        response = service._make_request(endpoint, method="GET", params=params)

        # BILL API v3 returns data in 'results' array
        bills_data = response.get("results", [])

        if not bills_data and response.get("status") == "error":
            raise UserError(
                _(f"BILL API error: {response.get('errorMessage', 'Unknown error')}")
            )

        _logger.info(
            f"Fetched {len(bills_data)} bills from BILL "
            f"with filters: {params.get('filters', 'none')}"
        )

        for bill_data in bills_data:
            billcom_bill_id = bill_data.get("id")

            # Check if bill exists in Odoo
            move = self.env["account.move"].search(
                [("billcom_id", "=", billcom_bill_id)], limit=1
            )

            queue_item = self.env["billcom.sync.queue"].create(
                {
                    "sync_type": "bill",
                    "record_model": "account.move",
                    "record_id": move.id if move else None,
                    "direction": self.sync_direction,
                    "operation": "update" if move else "create",
                    "priority": self.priority,
                    "state": "queued",
                    "billcom_id": billcom_bill_id,
                    "sync_data": str(bill_data),
                }
            )
            queue_items.append(queue_item)

        return queue_items

    def _fetch_payments_from_billcom(self, service, config):
        """Fetch payments from BILL API and create queue items"""
        queue_items = []

        # Build API filters using BILL API v3 format
        params = self._build_billcom_filters("payment")
        endpoint = "payments"

        _logger.info(f"Calling BILL API endpoint: {endpoint} with params: {params}")

        # Call BILL API with params dictionary
        response = service._make_request(endpoint, method="GET", params=params)

        # BILL API v3 returns data in 'results' array
        payments_data = response.get("results", [])

        if not payments_data and response.get("status") == "error":
            raise UserError(
                _(f"BILL API error: {response.get('errorMessage', 'Unknown error')}")
            )

        _logger.info(
            f"Fetched {len(payments_data)} payments from BILL "
            f"with filters: {params.get('filters', 'none')}"
        )

        for payment_data in payments_data:
            billcom_payment_id = payment_data.get("id")

            # Check if payment exists in Odoo
            payment = self.env["account.payment"].search(
                [("billcom_id", "=", billcom_payment_id)], limit=1
            )

            queue_item = self.env["billcom.sync.queue"].create(
                {
                    "sync_type": "payment",
                    "record_model": "account.payment",
                    "record_id": payment.id if payment else None,
                    "direction": self.sync_direction,
                    "operation": "update" if payment else "create",
                    "priority": self.priority,
                    "state": "queued",
                    "billcom_id": billcom_payment_id,
                    "sync_data": str(payment_data),
                }
            )
            queue_items.append(queue_item)

        return queue_items

    def _fetch_invoices_from_billcom(self, service, config):
        """Fetch invoices from BILL API and create queue items"""
        queue_items = []

        # Build API filters using BILL API v3 format
        params = self._build_billcom_filters("invoice")
        endpoint = "invoices"

        _logger.info(f"Calling BILL API endpoint: {endpoint} with params: {params}")

        # Call BILL API with params dictionary
        response = service._make_request(endpoint, method="GET", params=params)

        # BILL API v3 returns data in 'results' array
        invoices_data = response.get("results", []) if response else []

        if not invoices_data and response and response.get("status") == "error":
            raise UserError(
                _(f"BILL API error: {response.get('errorMessage', 'Unknown error')}")
            )

        _logger.info(
            f"Fetched {len(invoices_data)} invoices from BILL "
            f"with filters: {params.get('filters', 'none')}"
        )

        for invoice_data in invoices_data:
            billcom_invoice_id = invoice_data.get("id")

            # Check if invoice exists in Odoo
            move = self.env["account.move"].search(
                [("billcom_id", "=", billcom_invoice_id)], limit=1
            )

            queue_item = self.env["billcom.sync.queue"].create(
                {
                    "sync_type": "invoice",
                    "record_model": "account.move",
                    "record_id": move.id if move else None,
                    "direction": self.sync_direction,
                    "operation": "update" if move else "create",
                    "priority": self.priority,
                    "state": "queued",
                    "billcom_id": billcom_invoice_id,
                    "sync_data": str(invoice_data),
                }
            )
            queue_items.append(queue_item)

        return queue_items

    def _create_partner_sync_items(self, partner_type):
        """Create sync items for partners (vendors/customers)"""
        domain = []

        # Partner type filter
        if partner_type == "vendor":
            domain.append(("supplier_rank", ">", 0))
        else:
            domain.append(("customer_rank", ">", 0))

        # For Odoo → Bill.com: only sync new records (no billcom_id)
        if self.sync_direction == "odoo_to_billcom":
            domain.append(("billcom_id", "=", False))

        # Bill.com enabled filter
        if self.only_billcom_enabled:
            domain.append(("is_sync_to_billcom", "=", True))

        # Partner filter
        if self.filter_by_partner and self.partner_ids:
            domain.append(("id", "in", self.partner_ids.ids))

        # Date filter (using write_date as proxy)
        if self.filter_by_date and self.date_from and self.date_to:
            domain.extend(
                [
                    ("write_date", ">=", self.date_from),
                    ("write_date", "<=", self.date_to + timedelta(days=1)),
                ]
            )

        partners = self.env["res.partner"].search(domain)

        queue_items = []
        for partner in partners:
            queue_item = self.env["billcom.sync.queue"].create_sync_item(
                sync_type=partner_type,
                record_model="res.partner",
                record_id=partner.id,
                direction=self.sync_direction,
                priority=self.priority,
            )
            queue_items.append(queue_item)

        return queue_items

    def _create_bill_sync_items(self):
        """Create sync items for bills"""
        domain = [
            ("move_type", "=", "in_invoice"),  # Vendor bills only
            ("state", "in", ["draft", "posted"]),
        ]

        # For Odoo → Bill.com: only sync new records (no billcom_id)
        if self.sync_direction == "odoo_to_billcom":
            domain.append(("billcom_id", "=", False))

        # Bill.com enabled filter
        if self.only_billcom_enabled:
            domain.extend(
                [
                    ("partner_id.is_sync_to_billcom", "=", True),
                ]
            )

        # Partner filter
        if self.filter_by_partner and self.partner_ids:
            domain.append(("partner_id", "in", self.partner_ids.ids))

        # Date filter
        if self.filter_by_date and self.date_from and self.date_to:
            domain.extend(
                [
                    ("invoice_date", ">=", self.date_from),
                    ("invoice_date", "<=", self.date_to),
                ]
            )

        bills = self.env["account.move"].search(domain)

        queue_items = []
        for bill in bills:
            queue_item = self.env["billcom.sync.queue"].create_sync_item(
                sync_type="bill",
                record_model="account.move",
                record_id=bill.id,
                direction=self.sync_direction,
                priority=self.priority,
            )
            queue_items.append(queue_item)

        return queue_items

    def _create_invoice_sync_items(self):
        """Create sync items for customer invoices"""
        domain = [
            ("move_type", "=", "out_invoice"),  # Customer invoices only
            ("state", "in", ["draft", "posted"]),
        ]

        # For Odoo → Bill.com: only sync new records (no billcom_id)
        if self.sync_direction == "odoo_to_billcom":
            domain.append(("billcom_id", "=", False))

        # Bill.com enabled filter
        if self.only_billcom_enabled:
            domain.extend(
                [
                    ("partner_id.is_sync_to_billcom", "=", True),
                ]
            )

        # Partner filter
        if self.filter_by_partner and self.partner_ids:
            domain.append(("partner_id", "in", self.partner_ids.ids))

        # Date filter
        if self.filter_by_date and self.date_from and self.date_to:
            domain.extend(
                [
                    ("invoice_date", ">=", self.date_from),
                    ("invoice_date", "<=", self.date_to),
                ]
            )

        invoices = self.env["account.move"].search(domain)

        queue_items = []
        for invoice in invoices:
            queue_item = self.env["billcom.sync.queue"].create_sync_item(
                sync_type="invoice",
                record_model="account.move",
                record_id=invoice.id,
                direction=self.sync_direction,
                priority=self.priority,
            )
            queue_items.append(queue_item)

        return queue_items

    def _create_payment_sync_items(self):
        """Create sync items for payments"""
        domain = [
            ("payment_type", "=", "outbound"),
            ("partner_type", "=", "supplier"),
            ("state", "in", ["draft", "posted"]),
        ]

        # For Odoo → Bill.com: only sync new records (no billcom_id)
        if self.sync_direction == "odoo_to_billcom":
            domain.append(("billcom_id", "=", False))

        # Bill.com enabled filter
        if self.only_billcom_enabled:
            domain.extend(
                [
                    ("is_sync_to_billcom", "=", True),
                    ("partner_id.is_sync_to_billcom", "=", True),
                ]
            )

        # Partner filter
        if self.filter_by_partner and self.partner_ids:
            domain.append(("partner_id", "in", self.partner_ids.ids))

        # Date filter
        if self.filter_by_date and self.date_from and self.date_to:
            domain.extend(
                [
                    ("date", ">=", self.date_from),
                    ("date", "<=", self.date_to),
                ]
            )

        payments = self.env["account.payment"].search(domain)

        queue_items = []
        for payment in payments:
            queue_item = self.env["billcom.sync.queue"].create_sync_item(
                sync_type="payment",
                record_model="account.payment",
                record_id=payment.id,
                direction=self.sync_direction,
                priority=self.priority,
            )
            queue_items.append(queue_item)

        return queue_items

    def _create_document_sync_items(self):
        if self.sync_direction == "from_billcom":
            return []

        # Find billcom.document records that need to be synced
        domain = [
            ("bill_id", "!=", False),
            ("upload_status", "in", ["pending", "failed"]),
        ]

        if self.filter_by_date and self.date_from and self.date_to:
            domain.extend(
                [
                    ("create_date", ">=", self.date_from),
                    ("create_date", "<=", self.date_to + timedelta(days=1)),
                ]
            )

        documents = self.env["billcom.document"].search(domain)

        # Filter documents that belong to synced bills
        filtered_documents = documents.filtered(
            lambda d: d.bill_id
            and d.bill_id.billcom_id
            and d.bill_id.partner_id.is_sync_to_billcom
        )

        queue_items = []
        for document in filtered_documents:
            queue_item = self.env["billcom.sync.queue"].create_sync_item(
                sync_type="document",
                record_model="billcom.document",
                record_id=document.id,
                direction=self.sync_direction,
                priority=self.priority,
            )
            queue_items.append(queue_item)

        return queue_items

    def _process_sync_items(self, queue_items):
        """Process sync items immediately using optimized service methods"""
        total_processed = 0
        total_errors = 0
        service = self.env["billcom.service"]

        # Check if items are from Bill.com (have sync_data)
        if queue_items and queue_items[0].sync_data:
            # Bill.com → Odoo: Process each item individually
            for item in queue_items:
                try:
                    result = service.process_queue_item_from_billcom(item)
                    if result:
                        item.write({"state": "success"})
                        total_processed += 1
                    else:
                        item.write({"state": "error"})
                        total_errors += 1
                except Exception as e:
                    _logger.error(
                        f"Error processing {item.sync_type} item {item.id} from Bill.com: {e}"
                    )
                    item.write({"state": "error", "error_message": str(e)})
                    total_errors += 1
        else:
            # Odoo → Bill.com: Use optimized batch processing
            items_by_type = {}
            for item in queue_items:
                sync_type = item.sync_type
                if sync_type not in items_by_type:
                    items_by_type[sync_type] = []
                items_by_type[sync_type].append(item)

            for sync_type, items in items_by_type.items():
                try:
                    if sync_type == "vendor":
                        result = self._process_vendor_items(items, service)
                    elif sync_type == "customer":
                        result = self._process_customer_items(items, service)
                    elif sync_type == "bill":
                        result = self._process_bill_items(items, service)
                    elif sync_type == "invoice":
                        result = self._process_invoice_items(items, service)
                    elif sync_type == "payment":
                        result = self._process_payment_items(items, service)
                    elif sync_type == "document":
                        result = self._process_document_items(items, service)
                    else:
                        _logger.warning(f"Unknown sync type: {sync_type}")
                        result = {"processed": 0, "errors": len(items)}

                    # Normalize result keys (some methods return 'synced', others 'processed')
                    processed_count = result.get("processed", result.get("synced", 0))
                    error_count = (
                        len(result.get("errors", []))
                        if isinstance(result.get("errors"), list)
                        else result.get("errors", 0)
                    )

                    total_processed += processed_count
                    total_errors += error_count

                    # Update queue items state
                    for item in items:
                        if processed_count > 0:
                            item.write({"state": "success"})
                        else:
                            item.write({"state": "error"})

                except Exception as e:
                    _logger.error(f"Error processing {sync_type} items: {e}")
                    total_errors += len(items)
                    # Mark all items as failed
                    for item in items:
                        item.write({"state": "error"})

        return {
            "processed": total_processed,
            "errors": total_errors,
            "total": len(queue_items),
        }

    def _process_vendor_items(self, items, service):
        """Process vendor sync items"""
        # Build domain from items
        vendor_ids = [
            item.record_id for item in items if item.record_model == "res.partner"
        ]
        domain = [("id", "in", vendor_ids)]

        # Apply filters
        if self.only_billcom_enabled:
            domain.append(("is_sync_to_billcom", "=", True))
        if self.filter_by_date and self.date_from and self.date_to:
            domain.extend(
                [
                    ("write_date", ">=", self.date_from),
                    ("write_date", "<=", self.date_to + timedelta(days=1)),
                ]
            )

        return service.sync_partners_by_type("vendor", domain)

    def _process_customer_items(self, items, service):
        """Process customer sync items"""
        # Build domain from items
        customer_ids = [
            item.record_id for item in items if item.record_model == "res.partner"
        ]
        domain = [("id", "in", customer_ids)]

        # Apply filters
        if self.only_billcom_enabled:
            domain.append(("is_sync_to_billcom", "=", True))
        if self.filter_by_date and self.date_from and self.date_to:
            domain.extend(
                [
                    ("write_date", ">=", self.date_from),
                    ("write_date", "<=", self.date_to + timedelta(days=1)),
                ]
            )

        return service.sync_partners_by_type("customer", domain)

    def _process_bill_items(self, items, service):
        """Process bill sync items"""
        # Build domain from items
        bill_ids = [
            item.record_id for item in items if item.record_model == "account.move"
        ]
        domain = [("id", "in", bill_ids)]

        # Apply filters
        if self.only_billcom_enabled:
            domain.append(("partner_id.is_sync_to_billcom", "=", True))
        if self.filter_by_date and self.date_from and self.date_to:
            domain.extend(
                [
                    ("invoice_date", ">=", self.date_from),
                    ("invoice_date", "<=", self.date_to),
                ]
            )

        return service.sync_bills_by_domain(domain)

    def _process_invoice_items(self, items, service):
        """Process invoice sync items"""
        # Build domain from items
        invoice_ids = [
            item.record_id for item in items if item.record_model == "account.move"
        ]
        domain = [("id", "in", invoice_ids)]

        # Apply filters
        if self.only_billcom_enabled:
            domain.append(("partner_id.is_sync_to_billcom", "=", True))
        if self.filter_by_date and self.date_from and self.date_to:
            domain.extend(
                [
                    ("invoice_date", ">=", self.date_from),
                    ("invoice_date", "<=", self.date_to),
                ]
            )

        return service.sync_invoices_by_domain(domain)

    def _process_payment_items(self, items, service):
        """Process payment sync items"""
        # Build domain from items
        payment_ids = [
            item.record_id for item in items if item.record_model == "account.payment"
        ]
        domain = [("id", "in", payment_ids)]

        # Apply filters
        if self.only_billcom_enabled:
            domain.extend(
                [
                    ("is_sync_to_billcom", "=", True),
                    ("partner_id.is_sync_to_billcom", "=", True),
                ]
            )
        if self.filter_by_date and self.date_from and self.date_to:
            domain.extend(
                [
                    ("date", ">=", self.date_from),
                    ("date", "<=", self.date_to),
                ]
            )

        return service.sync_payments_by_domain(domain)

    def _process_document_items(self, items, service):
        """Process Bill.com document sync items"""
        # Build domain from items
        document_ids = [
            item.record_id for item in items if item.record_model == "billcom.document"
        ]

        documents = self.env["billcom.document"].browse(document_ids)

        processed = 0
        errors = []

        for document in documents:
            try:
                # Upload document to Bill.com
                document.button_upload_to_billcom()
                processed += 1
            except Exception as e:
                _logger.error(f"Error uploading document {document.id}: {e}")
                errors.append(str(e))

        return {
            "processed": processed,
            "errors": errors,
        }

    def action_view_queue(self):
        """View the sync queue"""
        return {
            "type": "ir.actions.act_window",
            "name": "Bill.com Sync Queue",
            "res_model": "billcom.sync.queue",
            "view_mode": "tree,form",
            "domain": [("create_uid", "=", self.env.user.id)],
            "context": {"create": False},
        }

    def action_view_logs(self):
        """View sync logs"""
        return {
            "type": "ir.actions.act_window",
            "name": "Bill.com Sync Logs",
            "res_model": "billcom.logger",
            "view_mode": "tree,form",
            "domain": [("user_id", "=", self.env.user.id)],
            "context": {"create": False},
        }
