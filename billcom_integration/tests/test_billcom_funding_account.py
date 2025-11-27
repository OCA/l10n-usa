# Copyright 2025 Binhex - Simple Solutions
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from psycopg2 import IntegrityError

import odoo.tools
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import BillcomTestCommon


@tagged("post_install", "-at_install", "billcom")
class TestBillcomFundingAccount(BillcomTestCommon):
    """Tests for billcom.funding.account model"""

    @classmethod
    def setUpClass(cls, chart_template_ref=None):
        super().setUpClass(chart_template_ref=chart_template_ref)

        # Create test funding account
        cls.test_account = cls.env["billcom.funding.account"].create(
            {
                "billcom_id": "00f123",
                "bank_name": "Test Bank",
                "name_on_account": "Test Company",
                "account_number": "****1234",
                "routing_number": "123456789",
                "funding_type": "BANK_ACCOUNT",
                "account_type": "CHECKING",
                "owner_type": "BUSINESS",
                "status": "VERIFIED",
                "is_default_payables": True,
                "is_default_receivables": False,
                "company_id": cls.env.company.id,
            }
        )

    # ===== Compute Name Tests =====

    def test_compute_name_full_details(self):
        """Should compute name from bank name, account holder, and number"""
        self.test_account.invalidate_recordset()

        expected_name = "Test Bank (Test Company) [****1234]"
        self.assertEqual(self.test_account.name, expected_name)

    def test_compute_name_bank_only(self):
        """Should compute name from bank name only"""
        account = self.env["billcom.funding.account"].create(
            {
                "billcom_id": "00f456",
                "bank_name": "Another Bank",
                "company_id": self.env.company.id,
            }
        )

        self.assertEqual(account.name, "Another Bank")

    def test_compute_name_no_details(self):
        """Should use default name when no details available"""
        account = self.env["billcom.funding.account"].create(
            {
                "billcom_id": "00f789",
                "company_id": self.env.company.id,
            }
        )

        self.assertEqual(account.name, "Bill.com Funding Account")

    def test_compute_name_partial_details(self):
        """Should compute name from partial details"""
        account = self.env["billcom.funding.account"].create(
            {
                "billcom_id": "00f999",
                "bank_name": "Partial Bank",
                "account_number": "****5678",
                "company_id": self.env.company.id,
            }
        )

        self.assertEqual(account.name, "Partial Bank [****5678]")

    # ===== Sync Funding Accounts from Bill.com Tests =====

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service.BillcomService.get_funding_accounts"  # noqa B950
    )
    def test_sync_funding_accounts_create_new(self, mock_get):
        """Should create new funding accounts from Bill.com"""
        mock_get.return_value = [
            {
                "id": "00f888",
                "bankName": "New Bank",
                "nameOnAccount": "New Company",
                "accountNumber": "****9999",
                "routingNumber": "987654321",
                "type": "SAVINGS",
                "ownerType": "BUSINESS",
                "status": "VERIFIED",
                "archived": False,
                "accessToAdmins": True,
                "createdBy": "usr123",
                "default": {
                    "payables": False,
                    "receivables": True,
                },
            }
        ]

        result = self.env[
            "billcom.funding.account"
        ].sync_funding_accounts_from_billcom()

        self.assertEqual(result["created"], 1)
        self.assertEqual(result["updated"], 0)
        self.assertEqual(result["errors"], 0)

        new_account = self.env["billcom.funding.account"].search(
            [("billcom_id", "=", "00f888")]
        )
        self.assertTrue(new_account)
        self.assertEqual(new_account.bank_name, "New Bank")
        self.assertTrue(new_account.is_default_receivables)

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service.BillcomService.get_funding_accounts"  # noqa B950
    )
    def test_sync_funding_accounts_update_existing(self, mock_get):
        """Should update existing funding accounts from Bill.com"""
        mock_get.return_value = [
            {
                "id": "00f123",
                "bankName": "Updated Bank",
                "nameOnAccount": "Updated Company",
                "accountNumber": "****1234",
                "routingNumber": "123456789",
                "type": "CHECKING",
                "ownerType": "BUSINESS",
                "status": "PENDING",
                "archived": False,
                "accessToAdmins": False,
                "createdBy": "usr456",
                "default": {
                    "payables": True,
                    "receivables": True,
                },
            }
        ]

        result = self.env[
            "billcom.funding.account"
        ].sync_funding_accounts_from_billcom()

        self.assertEqual(result["created"], 0)
        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["errors"], 0)

        self.test_account.invalidate_recordset()
        self.assertEqual(self.test_account.bank_name, "Updated Bank")
        self.assertEqual(self.test_account.status, "PENDING")
        self.assertTrue(self.test_account.is_default_receivables)

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service.BillcomService.get_funding_accounts"  # noqa B950
    )
    def test_sync_funding_accounts_skip_without_id(self, mock_get):
        """Should skip accounts without Bill.com ID"""
        mock_get.return_value = [
            {
                "bankName": "No ID Bank",
                "nameOnAccount": "Test",
            }
        ]

        result = self.env[
            "billcom.funding.account"
        ].sync_funding_accounts_from_billcom()

        self.assertEqual(result["created"], 0)
        self.assertEqual(result["errors"], 1)

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service.BillcomService.get_funding_accounts"  # noqa B950
    )
    def test_sync_funding_accounts_handle_archived(self, mock_get):
        """Should set active=False for archived accounts"""
        mock_get.return_value = [
            {
                "id": "00f777",
                "bankName": "Archived Bank",
                "nameOnAccount": "Test",
                "archived": True,
                "default": {},
            }
        ]

        result = self.env[
            "billcom.funding.account"
        ].sync_funding_accounts_from_billcom()

        self.assertEqual(result["created"], 1)

        archived_account = self.env["billcom.funding.account"].search(
            [("billcom_id", "=", "00f777")]
        )
        self.assertFalse(archived_account.active)

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service.BillcomService.get_funding_accounts"  # noqa B950
    )
    def test_sync_funding_accounts_error_handling(self, mock_get):
        """Should handle errors during sync"""
        mock_get.side_effect = Exception("API Error")

        with self.assertRaises(UserError):
            self.env["billcom.funding.account"].sync_funding_accounts_from_billcom()

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service.BillcomService.get_funding_accounts"  # noqa B950
    )
    def test_sync_funding_accounts_multiple(self, mock_get):
        """Should sync multiple funding accounts"""
        mock_get.return_value = [
            {
                "id": "00f001",
                "bankName": "Bank 1",
                "default": {},
            },
            {
                "id": "00f002",
                "bankName": "Bank 2",
                "default": {},
            },
            {
                "id": "00f003",
                "bankName": "Bank 3",
                "default": {},
            },
        ]

        result = self.env[
            "billcom.funding.account"
        ].sync_funding_accounts_from_billcom()

        self.assertEqual(result["created"], 3)
        self.assertEqual(result["total"], 3)

    # ===== Prepare Funding Account Vals Tests =====

    def test_prepare_funding_account_vals_complete(self):
        """Should prepare complete values from Bill.com data"""
        account_data = {
            "id": "00f555",
            "bankName": "Complete Bank",
            "nameOnAccount": "Complete Account",
            "accountNumber": "****5555",
            "routingNumber": "555555555",
            "type": "SAVINGS",
            "ownerType": "PERSONAL",
            "status": "PENDING",
            "archived": False,
            "accessToAdmins": True,
            "createdBy": "usr999",
            "default": {
                "payables": True,
                "receivables": False,
            },
        }

        vals = self.env["billcom.funding.account"]._prepare_funding_account_vals(
            account_data
        )

        self.assertEqual(vals["billcom_id"], "00f555")
        self.assertEqual(vals["bank_name"], "Complete Bank")
        self.assertEqual(vals["name_on_account"], "Complete Account")
        self.assertEqual(vals["account_number"], "****5555")
        self.assertEqual(vals["routing_number"], "555555555")
        self.assertEqual(vals["account_type"], "SAVINGS")
        self.assertEqual(vals["owner_type"], "PERSONAL")
        self.assertEqual(vals["status"], "PENDING")
        self.assertTrue(vals["active"])
        self.assertTrue(vals["access_to_admins"])
        self.assertTrue(vals["is_default_payables"])
        self.assertFalse(vals["is_default_receivables"])

    def test_prepare_funding_account_vals_minimal(self):
        """Should prepare minimal values from Bill.com data"""
        account_data = {
            "id": "00f666",
            "bankName": "Minimal Bank",
        }

        vals = self.env["billcom.funding.account"]._prepare_funding_account_vals(
            account_data
        )

        self.assertEqual(vals["billcom_id"], "00f666")
        self.assertEqual(vals["bank_name"], "Minimal Bank")
        self.assertTrue(vals["active"])  # Default should be not archived
        self.assertFalse(vals["is_default_payables"])  # Default from empty dict
        self.assertFalse(vals["is_default_receivables"])

    def test_prepare_funding_account_vals_archived(self):
        """Should set active=False when archived"""
        account_data = {
            "id": "00f777",
            "bankName": "Archived",
            "archived": True,
        }

        vals = self.env["billcom.funding.account"]._prepare_funding_account_vals(
            account_data
        )

        self.assertFalse(vals["active"])

    # ===== Action Sync from Bill.com Tests =====

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service.BillcomService.get_funding_accounts"  # noqa B950
    )
    def test_action_sync_from_billcom_success(self, mock_get):
        """Should return success notification"""
        mock_get.return_value = [
            {
                "id": "00f111",
                "bankName": "Action Bank",
                "default": {},
            }
        ]

        result = self.env["billcom.funding.account"].action_sync_from_billcom()

        self.assertEqual(result["type"], "ir.actions.client")
        self.assertEqual(result["tag"], "display_notification")
        self.assertIn("Created: 1", result["params"]["message"])
        self.assertEqual(result["params"]["type"], "success")

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service.BillcomService.get_funding_accounts"  # noqa B950
    )
    def test_action_sync_from_billcom_with_errors(self, mock_get):
        """Should return warning notification when errors occur"""
        mock_get.return_value = [
            {
                "id": "00f222",
                "bankName": "Good Bank",
                "default": {},
            },
            {
                # Missing ID will cause error
                "bankName": "Bad Bank",
            },
        ]

        result = self.env["billcom.funding.account"].action_sync_from_billcom()

        self.assertEqual(result["params"]["type"], "warning")
        self.assertIn("Errors: 1", result["params"]["message"])

    # ===== CRUD and Validation Tests =====

    def test_create_funding_account_basic(self):
        """Should create basic funding account"""
        account = self.env["billcom.funding.account"].create(
            {
                "billcom_id": "00f333",
                "bank_name": "Basic Bank",
                "company_id": self.env.company.id,
            }
        )

        self.assertEqual(account.bank_name, "Basic Bank")
        self.assertTrue(account.active)

    @odoo.tools.mute_logger("odoo.sql_db")
    def test_unique_constraint_billcom_id_company(self):
        """Should enforce unique constraint on billcom_id + company_id"""
        with self.assertRaises(IntegrityError):
            self.env["billcom.funding.account"].create(
                {
                    "billcom_id": "00f123",  # Same as test_account
                    "bank_name": "Duplicate",
                    "company_id": self.env.company.id,
                }
            )

    def test_search_default_payables(self):
        """Should search for default payables account"""
        accounts = self.env["billcom.funding.account"].search(
            [("is_default_payables", "=", True)]
        )

        self.assertIn(self.test_account, accounts)

    def test_ordering(self):
        """Should order by defaults first, then name"""
        # Create accounts with different default settings
        account1 = self.env["billcom.funding.account"].create(
            {
                "billcom_id": "00f_a",
                "bank_name": "AAA Bank",
                "is_default_payables": False,
                "is_default_receivables": False,
                "company_id": self.env.company.id,
            }
        )
        account2 = self.env["billcom.funding.account"].create(
            {
                "billcom_id": "00f_b",
                "bank_name": "BBB Bank",
                "is_default_payables": False,
                "is_default_receivables": True,
                "company_id": self.env.company.id,
            }
        )

        accounts = self.env["billcom.funding.account"].search([])

        # Payables default should be first (test_account)
        # Then receivables default (account2)
        # Then others
        first_idx = accounts.ids.index(self.test_account.id)
        second_idx = accounts.ids.index(account2.id)
        third_idx = accounts.ids.index(account1.id)

        self.assertLess(first_idx, second_idx)
        self.assertLess(second_idx, third_idx)

    def test_active_toggle(self):
        """Should toggle active status"""
        self.assertTrue(self.test_account.active)

        self.test_account.active = False
        self.assertFalse(self.test_account.active)

        self.test_account.active = True
        self.assertTrue(self.test_account.active)

    def test_funding_account_types(self):
        """Should support different funding types"""
        types = ["BANK_ACCOUNT", "CARD_ACCOUNT", "WALLET", "AP_CARD"]

        for idx, funding_type in enumerate(types):
            account = self.env["billcom.funding.account"].create(
                {
                    "billcom_id": f"00f_type_{idx}",
                    "bank_name": f"Type {funding_type}",
                    "funding_type": funding_type,
                    "company_id": self.env.company.id,
                }
            )
            self.assertEqual(account.funding_type, funding_type)

    def test_account_statuses(self):
        """Should support different account statuses"""
        statuses = ["VERIFIED", "PENDING", "UNVERIFIED", "FAILED"]

        for idx, status in enumerate(statuses):
            account = self.env["billcom.funding.account"].create(
                {
                    "billcom_id": f"00f_status_{idx}",
                    "bank_name": f"Status {status}",
                    "status": status,
                    "company_id": self.env.company.id,
                }
            )
            self.assertEqual(account.status, status)
