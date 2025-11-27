# Copyright 2025 Binhex - Simple Solutions
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import logging
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import BillcomTestCommon

_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install", "billcom")
class TestBillcomSyncWizard(BillcomTestCommon):
    """Tests for billcom.sync.wizard model"""

    @classmethod
    def setUpClass(cls, chart_template_ref=None):
        super().setUpClass(chart_template_ref=chart_template_ref)

        # Create test data
        cls.test_date_from = fields.Date.today() - timedelta(days=30)
        cls.test_date_to = fields.Date.today()

        # Create wizard with default values
        cls.wizard = cls.env["billcom.sync.wizard"].create(
            {
                "sync_vendors": True,
                "sync_customers": False,
                "sync_bills": True,
                "sync_payments": True,
                "sync_direction": "billcom_to_odoo",
                "filter_by_date": True,
                "date_from": cls.test_date_from,
                "date_to": cls.test_date_to,
                "process_immediately": False,
                "batch_size": 50,
                "priority": "1",
            }
        )

        # Create vendor bill
        cls.vendor_bill = cls.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": cls.vendor_billcom.id,
                "invoice_date": fields.Date.today(),
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Test Product",
                            "quantity": 1,
                            "price_unit": 100.0,
                        },
                    )
                ],
            }
        )

    # ===== Onchange Tests =====

    def test_onchange_filter_by_date_enable(self):
        """Should set default dates when enabling date filter"""
        wizard = self.env["billcom.sync.wizard"].create(
            {
                "filter_by_date": False,
                "date_from": False,
                "date_to": False,
            }
        )

        wizard.filter_by_date = True
        wizard._onchange_filter_by_date()

        self.assertTrue(wizard.date_from)
        self.assertTrue(wizard.date_to)

    def test_onchange_filter_by_partner_disable(self):
        """Should clear partners when disabling partner filter"""
        wizard = self.env["billcom.sync.wizard"].create(
            {
                "filter_by_partner": True,
                "partner_ids": [(6, 0, [self.vendor_billcom.id])],
            }
        )

        wizard.filter_by_partner = False
        wizard._onchange_filter_by_partner()

        self.assertFalse(wizard.partner_ids)

    # ===== Date Validation Tests =====

    def test_check_dates_invalid_range(self):
        """Should raise error if date_from > date_to"""
        with self.assertRaises(UserError) as context:
            self.env["billcom.sync.wizard"].create(
                {
                    "date_from": fields.Date.today(),
                    "date_to": fields.Date.today() - timedelta(days=10),
                }
            )

        self.assertIn("must be earlier than", str(context.exception))

    def test_check_dates_valid_range(self):
        """Should not raise error with valid date range"""
        wizard = self.env["billcom.sync.wizard"].create(
            {
                "date_from": fields.Date.today() - timedelta(days=10),
                "date_to": fields.Date.today(),
            }
        )

        self.assertTrue(wizard.id)

    # ===== Build Filters Tests =====

    def test_build_billcom_filters_vendor_basic(self):
        """Should build basic vendor filters"""
        result = self.wizard._build_billcom_filters("vendor")

        filters_str = result.get("filters", "")
        self.assertIn("archived:eq:false", filters_str)
        self.assertIn("createdTime:gte:", filters_str)
        self.assertIn("createdTime:lte:", filters_str)

    def test_build_billcom_filters_vendor_with_account_type(self):
        """Should include account type filter for vendors"""
        self.wizard.filter_vendor_account_type = "BUSINESS"
        result = self.wizard._build_billcom_filters("vendor")

        filters_str = result.get("filters", "")
        self.assertIn("accountType: eq: BUSINESS", filters_str)

    def test_build_billcom_filters_vendor_with_currency(self):
        """Should include currency filter for vendors"""
        usd = self.env.ref("base.USD")
        self.wizard.filter_vendor_currency = usd
        result = self.wizard._build_billcom_filters("vendor")

        filters_str = result.get("filters", "")
        self.assertIn("billCurrency: eq: USD", filters_str)

    def test_build_billcom_filters_bill_with_status(self):
        """Should include payment status filter for bills"""
        # Create bill status if not exists
        bill_status = (
            self.env["billcom.bill.status"]
            .sudo()
            .create({"name": "Unpaid", "code": "0"})
        )
        self.wizard.filter_bill_status = [(6, 0, [bill_status.id])]
        result = self.wizard._build_billcom_filters("bill")

        filters_str = result.get("filters", "")
        self.assertIn("paymentStatus: eq: 0", filters_str)

    def test_build_billcom_filters_without_dates(self):
        """Should not include date filters when disabled"""
        self.wizard.filter_by_date = False
        result = self.wizard._build_billcom_filters("vendor")

        filters_str = result.get("filters", "")
        self.assertNotIn("createdTime", filters_str)

    def test_build_billcom_filters_with_partner_single(self):
        """Should include single partner ID filter"""
        self.wizard.filter_by_partner = True
        self.wizard.partner_ids = [(6, 0, [self.vendor_billcom.id])]
        result = self.wizard._build_billcom_filters("vendor")

        filters_str = result.get("filters", "")
        if self.vendor_billcom.billcom_id:
            self.assertIn("id: eq:", filters_str)

    # ===== Action Start Sync Tests =====

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa: B950
    )
    def test_action_start_sync_success(self, mock_request):
        """Should start sync successfully"""
        mock_request.return_value = {
            "results": [
                {
                    "id": "00v001",
                    "name": "Test Vendor",
                    "email": "test@vendor.com",
                    "archived": False,
                }
            ],
            "nextPage": None,
        }

        result = self.wizard.action_start_sync()

        self.assertEqual(result["type"], "ir.actions.act_window")
        self.assertEqual(result["res_model"], "billcom.sync.wizard")
        self.assertTrue(self.wizard.result_summary)

    def test_action_start_sync_no_config(self):
        """Should raise error if no configuration"""
        # Disable config
        self.billcom_config.write({"active": False})

        with self.assertRaises(UserError) as context:
            self.wizard.action_start_sync()

        self.assertIn("No active Bill.com configuration", str(context.exception))

        # Re-enable config
        self.billcom_config.write({"active": True})

    def test_action_start_sync_no_sync_types(self):
        """Should raise error if no sync types selected"""
        wizard = self.env["billcom.sync.wizard"].create(
            {
                "sync_vendors": False,
                "sync_customers": False,
                "sync_bills": False,
                "sync_payments": False,
                "sync_invoices": False,
                "sync_documents": False,
            }
        )

        with self.assertRaises(UserError) as context:
            wizard.action_start_sync()

        self.assertIn("Please select at least one sync type", str(context.exception))

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa: B950
    )
    def test_action_start_sync_no_records(self, mock_request):
        """Should raise error if no records found"""
        mock_request.return_value = {"results": [], "nextPage": None}

        with self.assertRaises(UserError) as context:
            self.wizard.action_start_sync()

        self.assertIn("No records found", str(context.exception))

    # ===== Fetch from Bill.com Tests =====

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa: B950
    )
    def test_fetch_vendors_from_billcom_success(self, mock_request):
        """Should fetch vendors from Bill.com"""
        mock_request.return_value = {
            "results": [
                {
                    "id": "00v123",
                    "name": "Vendor 1",
                    "email": "vendor1@test.com",
                    "archived": False,
                },
                {
                    "id": "00v456",
                    "name": "Vendor 2",
                    "email": "vendor2@test.com",
                    "archived": False,
                },
            ],
            "nextPage": None,
        }

        service = self.env["billcom.service"]
        config = self.billcom_config

        queue_items = self.wizard._fetch_vendors_from_billcom(service, config)

        self.assertEqual(len(queue_items), 2)
        self.assertEqual(queue_items[0].sync_type, "vendor")
        self.assertEqual(queue_items[0].billcom_id, "00v123")

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa: B950
    )
    def test_fetch_customers_from_billcom_success(self, mock_request):
        """Should fetch customers from Bill.com"""
        mock_request.return_value = {
            "results": [
                {
                    "id": "00c123",
                    "name": "Customer 1",
                    "email": "customer1@test.com",
                    "archived": False,
                }
            ],
            "nextPage": None,
        }

        service = self.env["billcom.service"]
        config = self.billcom_config

        queue_items = self.wizard._fetch_customers_from_billcom(service, config)

        self.assertEqual(len(queue_items), 1)
        self.assertEqual(queue_items[0].sync_type, "customer")
        self.assertEqual(queue_items[0].billcom_id, "00c123")

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa: B950
    )
    def test_fetch_bills_from_billcom_success(self, mock_request):
        """Should fetch bills from Bill.com"""
        mock_request.return_value = {
            "results": [
                {
                    "id": "00b123",
                    "invoiceNumber": "BILL-001",
                    "vendorId": "00v123",
                    "paymentStatus": "0",
                }
            ],
            "nextPage": None,
        }

        service = self.env["billcom.service"]
        config = self.billcom_config

        queue_items = self.wizard._fetch_bills_from_billcom(service, config)

        self.assertEqual(len(queue_items), 1)
        self.assertEqual(queue_items[0].sync_type, "bill")
        self.assertEqual(queue_items[0].billcom_id, "00b123")

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa: B950
    )
    def test_fetch_payments_from_billcom_success(self, mock_request):
        """Should fetch payments from Bill.com"""
        mock_request.return_value = {
            "results": [
                {
                    "id": "00p123",
                    "vendorId": "00v123",
                    "amount": "100.00",
                    "status": "1",
                }
            ],
            "nextPage": None,
        }

        service = self.env["billcom.service"]
        config = self.billcom_config

        queue_items = self.wizard._fetch_payments_from_billcom(service, config)

        self.assertEqual(len(queue_items), 1)
        self.assertEqual(queue_items[0].sync_type, "payment")
        self.assertEqual(queue_items[0].billcom_id, "00p123")

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa: B950
    )
    def test_fetch_invoices_from_billcom_success(self, mock_request):
        """Should fetch invoices from Bill.com"""
        mock_request.return_value = {
            "results": [
                {
                    "id": "00i123",
                    "invoiceNumber": "INV-001",
                    "customerId": "00c123",
                    "status": "1",
                }
            ],
            "nextPage": None,
        }

        service = self.env["billcom.service"]
        config = self.billcom_config

        queue_items = self.wizard._fetch_invoices_from_billcom(service, config)

        self.assertEqual(len(queue_items), 1)
        self.assertEqual(queue_items[0].sync_type, "invoice")
        self.assertEqual(queue_items[0].billcom_id, "00i123")

    # ===== Create Sync Items from Odoo Tests =====

    def test_create_partner_sync_items_vendor(self):
        """Should create sync items for vendors"""
        # Mark vendor for sync
        self.vendor_billcom.write({"is_sync_to_billcom": True, "billcom_id": False})

        wizard = self.env["billcom.sync.wizard"].create(
            {
                "sync_direction": "odoo_to_billcom",
                "only_billcom_enabled": True,
                "filter_by_date": False,
            }
        )

        queue_items = wizard._create_partner_sync_items("vendor")

        self.assertGreater(len(queue_items), 0)
        self.assertEqual(queue_items[0].sync_type, "vendor")
        self.assertEqual(queue_items[0].direction, "odoo_to_billcom")

    def test_create_partner_sync_items_customer(self):
        """Should create sync items for customers"""
        # Mark customer for sync
        self.customer_billcom.write({"is_sync_to_billcom": True, "billcom_id": False})

        wizard = self.env["billcom.sync.wizard"].create(
            {
                "sync_direction": "odoo_to_billcom",
                "only_billcom_enabled": True,
                "filter_by_date": False,
            }
        )

        queue_items = wizard._create_partner_sync_items("customer")

        self.assertGreater(len(queue_items), 0)
        self.assertEqual(queue_items[0].sync_type, "customer")

    # def test_create_bill_sync_items(self):
    #     """Should create sync items for bills"""
    #     # Mark bill partner for sync
    #     self.vendor_bill.partner_id.write({"is_sync_to_billcom": True})
    #     self.vendor_bill.write({"billcom_id": False, "state": "draft"})

    #     wizard = self.env["billcom.sync.wizard"].create(
    #         {
    #             "sync_direction": "odoo_to_billcom",
    #             "only_billcom_enabled": True,
    #             "filter_by_date": False,
    #         }
    #     )

    #     queue_items = wizard._create_bill_sync_items()

    #     self.assertGreater(len(queue_items), 0)
    #     self.assertEqual(queue_items[0].sync_type, "bill")
    #     self.assertEqual(queue_items[0].record_model, "account.move")

    # def test_create_payment_sync_items(self):
    #     """Should create sync items for payments"""
    #     # Create payment
    #     payment = self.env["account.payment"].create(
    #         {
    #             "payment_type": "outbound",
    #             "partner_type": "supplier",
    #             "partner_id": self.vendor_billcom.id,
    #             "amount": 100.0,
    #             "date": fields.Date.today(),
    #             "is_sync_to_billcom": True,
    #         }
    #     )
    #     payment.partner_id.write({"is_sync_to_billcom": True})

    #     wizard = self.env["billcom.sync.wizard"].create(
    #         {
    #             "sync_direction": "odoo_to_billcom",
    #             "only_billcom_enabled": True,
    #             "filter_by_date": False,
    #         }
    #     )

    #     queue_items = wizard._create_payment_sync_items()

    #     self.assertGreater(len(queue_items), 0)
    #     self.assertEqual(queue_items[0].sync_type, "payment")

    # ===== Generate HTML Summary Tests =====

    def test_generate_html_summary_with_stats(self):
        """Should generate HTML summary with sync stats"""
        sync_stats = {
            "vendor": {"items": 5, "error": None},
            "bill": {"items": 3, "error": None},
        }
        total_items = 8

        html = self.wizard._generate_html_summary(sync_stats, total_items)

        self.assertIn("Synchronization Results", html)
        self.assertIn("vendor", html.lower())
        self.assertIn("bill", html.lower())
        self.assertIn("Items Queued", html)

    def test_generate_html_summary_with_errors(self):
        """Should show errors in HTML summary"""
        sync_stats = {
            "vendor": {"items": 0, "error": "API connection failed"},
        }
        total_items = 0

        html = self.wizard._generate_html_summary(sync_stats, total_items)

        self.assertIn("Error", html)
        self.assertIn("API connection", html)

    def test_generate_html_summary_with_processed_results(self):
        """Should show processing results in summary"""
        sync_stats = {
            "vendor": {"items": 10, "error": None},
        }
        total_items = 10
        processed_results = {
            "processed": 8,
            "errors": 2,
            "total": 10,
        }

        html = self.wizard._generate_html_summary(
            sync_stats, total_items, processed_results
        )

        self.assertIn("Processing Results", html)
        self.assertIn("8", html)  # Success count
        self.assertIn("2", html)  # Error count
        self.assertIn("Success Rate", html)

    # ===== Process Sync Items Tests =====

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service.BillcomService.process_queue_item_from_billcom"  # noqa: B950
    )
    def test_process_sync_items_from_billcom(self, mock_process):
        """Should process items from Bill.com"""
        mock_process.return_value = True

        # Create queue item with sync_data
        queue_item = self.env["billcom.sync.queue"].create(
            {
                "sync_type": "vendor",
                "direction": "billcom_to_odoo",
                "billcom_id": "00v123",
                "sync_data": json.dumps({"id": "00v123", "name": "Test Vendor"}),
                "state": "queued",
            }
        )

        result = self.wizard._process_sync_items([queue_item])

        self.assertEqual(result["processed"], 1)
        self.assertEqual(result["errors"], 0)
        self.assertEqual(queue_item.state, "success")

    # ===== Action View Tests =====

    def test_action_view_queue(self):
        """Should return action to view queue"""
        result = self.wizard.action_view_queue()

        self.assertEqual(result["type"], "ir.actions.act_window")
        self.assertEqual(result["res_model"], "billcom.sync.queue")
        self.assertEqual(result["view_mode"], "tree,form")

    def test_action_view_logs(self):
        """Should return action to view logs"""
        result = self.wizard.action_view_logs()

        self.assertEqual(result["type"], "ir.actions.act_window")
        self.assertEqual(result["res_model"], "billcom.logger")
        self.assertEqual(result["view_mode"], "tree,form")
