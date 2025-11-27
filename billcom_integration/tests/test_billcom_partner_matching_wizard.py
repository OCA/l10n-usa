# Copyright 2025 Binhex - Simple Solutions
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import logging
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import BillcomTestCommon

_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install", "billcom")
class TestBillcomPartnerMatchingWizard(BillcomTestCommon):
    """Tests for billcom.partner.matching.wizard and line models"""

    @classmethod
    def setUpClass(cls, chart_template_ref=None):
        super().setUpClass(chart_template_ref=chart_template_ref)

        # Create wizard
        cls.wizard = cls.env["billcom.partner.matching.wizard"].create(
            {
                "partner_type": "vendor",
                "state": "draft",
            }
        )

        # Create test partners
        cls.test_vendor = cls.env["res.partner"].create(
            {
                "name": "Test Vendor Inc",
                "email": "test@vendor.com",
                "phone": "+1-555-123-4567",
                "supplier_rank": 1,
            }
        )

        cls.test_vendor_linked = cls.env["res.partner"].create(
            {
                "name": "Linked Vendor",
                "billcom_id": "00v123linked",
                "email": "linked@vendor.com",
                "supplier_rank": 1,
            }
        )

    # ===== Wizard - Compute Stats Tests =====

    def test_compute_stats_with_lines(self):
        """Should compute stats from lines"""
        # Create lines with different confidence levels
        self.env["billcom.partner.matching.line"].create(
            {
                "wizard_id": self.wizard.id,
                "billcom_partner_id": "00v001",
                "billcom_partner_name": "High Confidence",
                "confidence_level": "high",
                "selected": True,
            }
        )
        self.env["billcom.partner.matching.line"].create(
            {
                "wizard_id": self.wizard.id,
                "billcom_partner_id": "00v002",
                "billcom_partner_name": "Medium Confidence",
                "confidence_level": "medium",
            }
        )
        self.env["billcom.partner.matching.line"].create(
            {
                "wizard_id": self.wizard.id,
                "billcom_partner_id": "00v003",
                "billcom_partner_name": "No Match",
                "confidence_level": "none",
                "is_duplicate_group": True,
            }
        )

        self.assertEqual(self.wizard.total_partners, 3)
        self.assertEqual(self.wizard.high_confidence_count, 1)
        self.assertEqual(self.wizard.medium_confidence_count, 1)
        self.assertEqual(self.wizard.no_match_count, 1)
        self.assertEqual(self.wizard.selected_count, 1)
        self.assertEqual(self.wizard.duplicate_group_count, 1)

    # ===== Wizard - Normalize Partner Name Tests =====

    def test_normalize_partner_name_empty(self):
        """Should return empty string for None"""
        result = self.wizard._normalize_partner_name(None)
        self.assertEqual(result, "")

    # ===== Wizard - Group Duplicates Tests =====

    def test_group_billcom_duplicates_no_duplicates(self):
        """Should return empty duplicates dict when no duplicates"""
        billcom_partners = [
            {"id": "00v001", "name": "ABC Company"},
            {"id": "00v002", "name": "XYZ Corp"},
        ]

        _grouped, duplicates = self.wizard._group_billcom_duplicates(billcom_partners)

        self.assertEqual(len(duplicates), 0)

    # ===== Wizard - Normalize Text Tests =====

    def test_normalize_text_basic(self):
        """Should normalize text for comparison"""
        result = self.wizard._normalize_text("Test Company!!!")
        self.assertEqual(result, "test company")

    def test_normalize_text_remove_accents(self):
        """Should remove accents from text"""
        result = self.wizard._normalize_text("Société Générale")
        self.assertEqual(result, "societe generale")

    def test_normalize_text_empty(self):
        """Should return empty string for None"""
        result = self.wizard._normalize_text(None)
        self.assertEqual(result, "")

    # ===== Wizard - Normalize Phone Tests =====

    def test_normalize_phone_digits_only(self):
        """Should keep only digits"""
        test_cases = [
            ("+1-555-123-4567", "15551234567"),
            ("(555) 123-4567", "5551234567"),
            ("555.123.4567", "5551234567"),
        ]

        for input_phone, expected in test_cases:
            result = self.wizard._normalize_phone(input_phone)
            self.assertEqual(result, expected)

    def test_normalize_phone_empty(self):
        """Should return empty string for None"""
        result = self.wizard._normalize_phone(None)
        self.assertEqual(result, "")

    # ===== Wizard - Find Odoo Matches Tests =====

    def test_find_odoo_matches_high_confidence(self):
        """Should find high confidence match (3/3 criteria)"""
        billcom_partner = {
            "id": "00v123",
            "name": "Test Vendor Inc",
            "email": "test@vendor.com",
            "phone": "+1-555-123-4567",
        }

        matches = self.wizard._find_odoo_matches(
            billcom_partner, self.env["res.partner"].browse([self.test_vendor.id])
        )

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["confidence_level"], "high")
        self.assertEqual(matches[0]["score"], 3)

    def test_find_odoo_matches_medium_confidence(self):
        """Should find medium confidence match (2/3 criteria)"""
        billcom_partner = {
            "id": "00v123",
            "name": "Different Name",
            "email": "test@vendor.com",
            "phone": "+1-555-123-4567",
        }

        matches = self.wizard._find_odoo_matches(
            billcom_partner, self.env["res.partner"].browse([self.test_vendor.id])
        )

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["confidence_level"], "medium")
        self.assertEqual(matches[0]["score"], 2)

    def test_find_odoo_matches_low_confidence(self):
        """Should find low confidence match (1/3 criteria)"""
        billcom_partner = {
            "id": "00v123",
            "name": "Test Vendor Inc",
            "email": "different@email.com",
            "phone": "999-999-9999",
        }

        matches = self.wizard._find_odoo_matches(
            billcom_partner, self.env["res.partner"].browse([self.test_vendor.id])
        )

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["confidence_level"], "low")
        self.assertEqual(matches[0]["score"], 1)

    def test_find_odoo_matches_no_match(self):
        """Should return empty list when no criteria match"""
        billcom_partner = {
            "id": "00v123",
            "name": "Completely Different",
            "email": "different@email.com",
            "phone": "999-999-9999",
        }

        matches = self.wizard._find_odoo_matches(
            billcom_partner, self.env["res.partner"].browse([self.test_vendor.id])
        )

        self.assertEqual(len(matches), 0)

    # ===== Wizard - Action Find Matches Tests =====

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_action_find_matches_success(self, mock_request):
        """Should find matches between Odoo and Bill.com partners"""
        # Mock Bill.com API response
        mock_request.return_value = {
            "results": [
                {
                    "id": "00v001",
                    "name": "Test Vendor Inc",
                    "email": "test@vendor.com",
                    "phone": "+1-555-123-4567",
                    "archived": False,
                }
            ],
            "nextPage": None,
        }

        # Enable vendor sync
        self.billcom_config.write({"sync_vendors": True})

        result = self.wizard.action_find_matches()

        self.assertEqual(result["type"], "ir.actions.act_window")
        self.assertEqual(self.wizard.state, "review")
        self.assertGreater(len(self.wizard.line_ids), 0)

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_action_find_matches_sync_disabled(self, mock_request):
        """Should raise error if sync is disabled"""
        # Disable vendor sync
        self.billcom_config.write({"sync_vendors": False})

        with self.assertRaises(UserError) as context:
            self.wizard.action_find_matches()

        self.assertIn("disabled in configuration", str(context.exception))

    # ===== Wizard - Action Apply Selected Tests =====

    def test_action_apply_selected_no_selection(self):
        """Should raise error if no lines selected"""
        with self.assertRaises(UserError) as context:
            self.wizard.action_apply_selected()

        self.assertIn("No lines selected", str(context.exception))

    @patch(
        "odoo.addons.billcom_integration.wizards.billcom_partner_matching_line.BillcomPartnerMatchingLine.action_apply_link"  # noqa B950
    )
    def test_action_apply_selected_link_success(self, mock_link):
        """Should process selected link actions"""
        mock_link.return_value = None

        # Create selected line with link action
        self.env["billcom.partner.matching.line"].create(
            {
                "wizard_id": self.wizard.id,
                "odoo_partner_id": self.test_vendor.id,
                "billcom_partner_id": "00v123",
                "billcom_partner_name": "Test Vendor",
                "action": "link",
                "selected": True,
            }
        )

        result = self.wizard.action_apply_selected()

        self.assertEqual(result["type"], "ir.actions.client")
        mock_link.assert_called_once()

    # ===== Wizard - Selection Management Tests =====

    def test_action_select_all(self):
        """Should select all lines"""
        # Create lines
        for i in range(3):
            self.env["billcom.partner.matching.line"].create(
                {
                    "wizard_id": self.wizard.id,
                    "billcom_partner_id": f"00v{i}",
                    "billcom_partner_name": f"Partner {i}",
                }
            )

        self.wizard.action_select_all()

        selected = self.wizard.line_ids.filtered(lambda l: l.selected)
        self.assertEqual(len(selected), 3)

    def test_action_deselect_all(self):
        """Should deselect all lines"""
        # Create selected lines
        for i in range(3):
            self.env["billcom.partner.matching.line"].create(
                {
                    "wizard_id": self.wizard.id,
                    "billcom_partner_id": f"00v{i}",
                    "billcom_partner_name": f"Partner {i}",
                    "selected": True,
                }
            )

        self.wizard.action_deselect_all()

        selected = self.wizard.line_ids.filtered(lambda l: l.selected)
        self.assertEqual(len(selected), 0)

    def test_action_select_no_match(self):
        """Should select only no match lines"""
        # Create lines with different confidence levels
        self.env["billcom.partner.matching.line"].create(
            {
                "wizard_id": self.wizard.id,
                "billcom_partner_id": "00v001",
                "billcom_partner_name": "High",
                "confidence_level": "high",
            }
        )
        self.env["billcom.partner.matching.line"].create(
            {
                "wizard_id": self.wizard.id,
                "billcom_partner_id": "00v002",
                "billcom_partner_name": "No Match",
                "confidence_level": "none",
            }
        )

        self.wizard.action_select_no_match()

        selected = self.wizard.line_ids.filtered(lambda l: l.selected)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected.confidence_level, "none")

    def test_action_select_high_confidence(self):
        """Should select only high confidence lines"""
        # Create lines
        self.env["billcom.partner.matching.line"].create(
            {
                "wizard_id": self.wizard.id,
                "billcom_partner_id": "00v001",
                "billcom_partner_name": "High",
                "confidence_level": "high",
            }
        )
        self.env["billcom.partner.matching.line"].create(
            {
                "wizard_id": self.wizard.id,
                "billcom_partner_id": "00v002",
                "billcom_partner_name": "Medium",
                "confidence_level": "medium",
            }
        )

        self.wizard.action_select_high_confidence()

        selected = self.wizard.line_ids.filtered(lambda l: l.selected)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected.confidence_level, "high")

    # ===== Wizard - Bulk Set Actions Tests =====

    def test_action_bulk_set_link(self):
        """Should set selected lines to link action"""
        # Create selected line with odoo partner
        line = self.env["billcom.partner.matching.line"].create(
            {
                "wizard_id": self.wizard.id,
                "odoo_partner_id": self.test_vendor.id,
                "billcom_partner_id": "00v123",
                "billcom_partner_name": "Test",
                "selected": True,
            }
        )

        self.wizard.action_bulk_set_link()

        self.assertEqual(line.action, "link")

    def test_action_bulk_set_create(self):
        """Should set selected lines to create action"""
        line = self.env["billcom.partner.matching.line"].create(
            {
                "wizard_id": self.wizard.id,
                "billcom_partner_id": "00v123",
                "billcom_partner_name": "Test",
                "selected": True,
            }
        )

        self.wizard.action_bulk_set_create()

        self.assertEqual(line.action, "create")

    def test_action_bulk_set_ignore(self):
        """Should set selected lines to ignore action"""
        line = self.env["billcom.partner.matching.line"].create(
            {
                "wizard_id": self.wizard.id,
                "billcom_partner_id": "00v123",
                "billcom_partner_name": "Test",
                "selected": True,
            }
        )

        self.wizard.action_bulk_set_ignore()

        self.assertEqual(line.action, "ignore")

    # ===== Wizard - Reset Tests =====

    def test_action_reset(self):
        """Should reset wizard to draft state"""
        # Create lines
        self.env["billcom.partner.matching.line"].create(
            {
                "wizard_id": self.wizard.id,
                "billcom_partner_id": "00v123",
                "billcom_partner_name": "Test",
            }
        )

        self.wizard.write({"state": "review"})

        self.wizard.action_reset()

        self.assertEqual(self.wizard.state, "draft")
        self.assertEqual(len(self.wizard.line_ids), 0)

    def test_action_reset_all_billcom_ids(self):
        """Should reset all Bill.com IDs"""
        # Create partner with billcom_id
        partner = self.env["res.partner"].create(
            {
                "name": "Test Reset",
                "billcom_id": "00v999",
                "billcom": "00v999",
                "billcom_sync_status": "synced",
            }
        )

        result = self.wizard.action_reset_all_billcom_ids()

        self.assertEqual(result["type"], "ir.actions.client")
        self.assertFalse(partner.billcom_id)
        self.assertFalse(partner.billcom)
        self.assertEqual(partner.billcom_sync_status, "not_synced")

    # ===== Line - Compute Tests =====

    def test_line_compute_confidence_color(self):
        """Should compute correct color for confidence level"""
        color_cases = [
            ("high", 10),
            ("medium", 4),
            ("low", 2),
            ("none", 1),
        ]

        for confidence, expected_color in color_cases:
            line = self.env["billcom.partner.matching.line"].create(
                {
                    "wizard_id": self.wizard.id,
                    "billcom_partner_id": "00v123",
                    "billcom_partner_name": "Test",
                    "confidence_level": confidence,
                }
            )

            self.assertEqual(line.confidence_color, expected_color)

    def test_line_compute_billcom_ids_count_single(self):
        """Should return 1 for single Bill.com ID"""
        line = self.env["billcom.partner.matching.line"].create(
            {
                "wizard_id": self.wizard.id,
                "billcom_partner_id": "00v123",
                "billcom_partner_name": "Test",
            }
        )

        self.assertEqual(line.billcom_ids_count, 1)

    def test_line_compute_billcom_ids_count_duplicate_group(self):
        """Should count IDs in duplicate group"""
        billcom_ids = [
            {"id": "00v001", "currency": "USD"},
            {"id": "00v002", "currency": "EUR"},
        ]

        line = self.env["billcom.partner.matching.line"].create(
            {
                "wizard_id": self.wizard.id,
                "billcom_partner_id": "00v001",
                "billcom_partner_name": "Test Group",
                "is_duplicate_group": True,
                "billcom_ids_json": json.dumps(billcom_ids),
            }
        )

        self.assertEqual(line.billcom_ids_count, 2)

    # ===== Line - Action Apply Link Tests =====

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_line_action_apply_link_success(self, mock_request):
        """Should link partner successfully"""
        mock_request.return_value = {
            "id": "00v123",
            "name": "Test Vendor Inc",
            "email": "test@vendor.com",
            "phone": "+1-555-123-4567",
            "archived": False,
            "billCurrency": "USD",
        }

        line = self.env["billcom.partner.matching.line"].create(
            {
                "wizard_id": self.wizard.id,
                "odoo_partner_id": self.test_vendor.id,
                "billcom_partner_id": "00v123",
                "billcom_partner_name": "Test Vendor",
                "confidence_level": "high",
            }
        )

        line.action_apply_link()

        self.assertEqual(line.state, "linked")
        self.assertEqual(self.test_vendor.billcom_id, "00v123")

    def test_line_action_apply_link_no_billcom_id(self):
        """Should set error if no Bill.com ID"""
        line = self.env["billcom.partner.matching.line"].create(
            {
                "wizard_id": self.wizard.id,
                "odoo_partner_id": self.test_vendor.id,
                "billcom_partner_name": "Test",
            }
        )

        line.action_apply_link()

        self.assertEqual(line.state, "error")
        self.assertIn("No Bill.com partner", line.error_message)

    def test_line_action_apply_link_no_odoo_partner(self):
        """Should set error if no Odoo partner selected"""
        line = self.env["billcom.partner.matching.line"].create(
            {
                "wizard_id": self.wizard.id,
                "billcom_partner_id": "00v123",
                "billcom_partner_name": "Test",
            }
        )

        line.action_apply_link()

        self.assertEqual(line.state, "error")
        self.assertIn("No Odoo partner selected", line.error_message)

    def test_line_action_apply_link_already_linked(self):
        """Should set error if Odoo partner already has Bill.com ID"""
        line = self.env["billcom.partner.matching.line"].create(
            {
                "wizard_id": self.wizard.id,
                "odoo_partner_id": self.test_vendor_linked.id,
                "billcom_partner_id": "00v999",
                "billcom_partner_name": "Test",
            }
        )

        line.action_apply_link()

        self.assertEqual(line.state, "error")
        self.assertIn("already linked", line.error_message)

    # ===== Line - Action Apply Create Tests =====

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_line_action_apply_create_success(self, mock_request):
        """Should create new partner successfully"""
        mock_request.return_value = {
            "id": "00v123",
            "name": "New Vendor Inc",
            "email": "new@vendor.com",
            "phone": "+1-555-999-8888",
            "archived": False,
            "billCurrency": "USD",
            "accountType": "BUSINESS",
        }

        line = self.env["billcom.partner.matching.line"].create(
            {
                "wizard_id": self.wizard.id,
                "billcom_partner_id": "00v123",
                "billcom_partner_name": "New Vendor Inc",
                "action": "create",
            }
        )

        line.action_apply_create()

        self.assertEqual(line.state, "created")
        self.assertTrue(line.odoo_partner_id)
        self.assertEqual(line.odoo_partner_id.billcom_id, "00v123")

    def test_line_action_apply_create_no_billcom_id(self):
        """Should set error if no Bill.com ID"""
        line = self.env["billcom.partner.matching.line"].create(
            {
                "wizard_id": self.wizard.id,
                "billcom_partner_name": "Test",
                "action": "create",
            }
        )

        line.action_apply_create()

        self.assertEqual(line.state, "error")
        self.assertIn("No Bill.com partner", line.error_message)

    def test_line_action_apply_create_already_exists(self):
        """Should set error if partner already exists"""
        line = self.env["billcom.partner.matching.line"].create(
            {
                "wizard_id": self.wizard.id,
                "billcom_partner_id": "00v123linked",
                "billcom_partner_name": "Test",
                "action": "create",
            }
        )

        line.action_apply_create()

        self.assertEqual(line.state, "error")
        self.assertIn("already exists", line.error_message)

    # ===== Line - Other Actions Tests =====

    def test_line_action_ignore(self):
        """Should mark line as ignored"""
        line = self.env["billcom.partner.matching.line"].create(
            {
                "wizard_id": self.wizard.id,
                "billcom_partner_id": "00v123",
                "billcom_partner_name": "Test",
            }
        )

        line.action_ignore()

        self.assertEqual(line.action, "ignore")
        self.assertEqual(line.state, "ignored")

    def test_line_action_unlink_partner(self):
        """Should unlink Bill.com ID from partner"""
        line = self.env["billcom.partner.matching.line"].create(
            {
                "wizard_id": self.wizard.id,
                "odoo_partner_id": self.test_vendor_linked.id,
                "billcom_partner_id": "00v123",
                "billcom_partner_name": "Test",
            }
        )

        result = line.action_unlink_partner()

        self.assertEqual(result["type"], "ir.actions.client")
        self.assertFalse(self.test_vendor_linked.billcom_id)
        self.assertEqual(line.state, "pending")

    # ===== Line - Validate Parent Tests =====

    def test_line_validate_parent_no_parent(self):
        """Should return None for no parent"""
        line = self.env["billcom.partner.matching.line"].create(
            {
                "wizard_id": self.wizard.id,
                "billcom_partner_id": "00v123",
                "billcom_partner_name": "Test",
            }
        )

        result = line._validate_parent(None)
        self.assertFalse(result)

    def test_line_validate_parent_with_parent(self):
        """Should return parent for valid parent"""
        parent = self.env["res.partner"].create(
            {
                "name": "Parent Partner",
                "supplier_rank": 1,
            }
        )

        line = self.env["billcom.partner.matching.line"].create(
            {
                "wizard_id": self.wizard.id,
                "billcom_partner_id": "00v123",
                "billcom_partner_name": "Test",
            }
        )

        result = line._validate_parent(parent)
        self.assertEqual(result, parent)

    def test_line_validate_parent_prevent_recursion(self):
        """Should use grandparent if parent is a child"""
        grandparent = self.env["res.partner"].create(
            {
                "name": "Grandparent",
                "supplier_rank": 1,
            }
        )
        parent = self.env["res.partner"].create(
            {
                "name": "Parent Child",
                "parent_id": grandparent.id,
                "supplier_rank": 1,
            }
        )

        line = self.env["billcom.partner.matching.line"].create(
            {
                "wizard_id": self.wizard.id,
                "billcom_partner_id": "00v123",
                "billcom_partner_name": "Test",
            }
        )

        result = line._validate_parent(parent)
        self.assertEqual(result, grandparent)

    # ===== Line - Link Duplicate Group Tests =====

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa: B950
    )
    def test_line_link_duplicate_group_success(self, mock_request):
        """Should link duplicate group to existing partner"""
        mock_request.return_value = {
            "id": "00v123",
            "name": "Test Vendor",
            "email": "test@vendor.com",
            "archived": False,
            "billCurrency": "USD",
        }

        parent = self.env["res.partner"].create(
            {
                "name": "Parent Vendor",
                "supplier_rank": 1,
            }
        )

        billcom_ids = [
            {"id": "00v123", "currency": "USD"},
            {"id": "00v456", "currency": "EUR"},
        ]

        line = self.env["billcom.partner.matching.line"].create(
            {
                "wizard_id": self.wizard.id,
                "odoo_partner_id": parent.id,
                "billcom_partner_name": "Test Group",
                "is_duplicate_group": True,
                "billcom_ids_json": json.dumps(billcom_ids),
            }
        )

        line._link_duplicate_group_to_existing_partner()

        # Check children were created
        children = self.env["res.partner"].search([("parent_id", "=", parent.id)])
        self.assertGreater(len(children), 0)

    def test_line_link_duplicate_group_no_partner(self):
        """Should raise error if no Odoo partner selected"""
        billcom_ids = [{"id": "00v123", "currency": "USD"}]

        line = self.env["billcom.partner.matching.line"].create(
            {
                "wizard_id": self.wizard.id,
                "billcom_partner_name": "Test Group",
                "is_duplicate_group": True,
                "billcom_ids_json": json.dumps(billcom_ids),
            }
        )

        with self.assertRaises(UserError):
            line._link_duplicate_group_to_existing_partner()

    # ===== Line - Create Partner from Duplicate Group Tests =====

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa: B950
    )
    def test_line_create_partner_from_duplicate_group_success(self, mock_request):
        """Should create new parent with children for duplicate group"""
        mock_request.return_value = {
            "id": "00v123",
            "name": "Test Vendor",
            "email": "test@vendor.com",
            "phone": "555-1234",
            "archived": False,
            "billCurrency": "USD",
            "accountType": "BUSINESS",
        }

        billcom_ids = [
            {"id": "00v123", "currency": "USD"},
            {"id": "00v456", "currency": "EUR"},
        ]

        line = self.env["billcom.partner.matching.line"].create(
            {
                "wizard_id": self.wizard.id,
                "billcom_partner_id": "00v123",
                "billcom_partner_name": "Test Vendor Group",
                "billcom_partner_email": "test@vendor.com",
                "billcom_partner_phone": "555-1234",
                "is_duplicate_group": True,
                "billcom_ids_json": json.dumps(billcom_ids),
            }
        )

        line._create_partner_from_duplicate_group()

        # Verify line state
        self.assertEqual(line.state, "created")
        self.assertTrue(line.odoo_partner_id)

        # Verify parent was created
        parent = line.odoo_partner_id
        self.assertEqual(parent.name, "Test Vendor")

        # Verify children were created
        children = self.env["res.partner"].search([("parent_id", "=", parent.id)])
        self.assertGreater(len(children), 0)

    # ===== Line - Action Select for Link Tests =====

    def test_line_action_select_for_link(self):
        """Should set action to link"""
        line = self.env["billcom.partner.matching.line"].create(
            {
                "wizard_id": self.wizard.id,
                "odoo_partner_id": self.test_vendor.id,
                "billcom_partner_id": "00v123",
                "billcom_partner_name": "Test",
            }
        )

        line.action_select_for_link()

        self.assertEqual(line.action, "link")
