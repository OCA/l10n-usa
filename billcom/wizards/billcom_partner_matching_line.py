# Copyright 2025 Binhex
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class BillcomPartnerMatchingLine(models.TransientModel):
    _name = "billcom.partner.matching.line"
    _description = "Bill.com Partner Matching Line"
    _order = "confidence_level desc, match_score desc, id"

    wizard_id = fields.Many2one(
        "billcom.partner.matching.wizard",
        string="Wizard",
        required=True,
        ondelete="cascade",
    )
    selected = fields.Boolean(
        string="Select",
        default=False,
        help="Select this line for bulk actions",
    )
    odoo_partner_id = fields.Many2one("res.partner", string="Odoo Partner")
    odoo_partner_name = fields.Char(
        related="odoo_partner_id.name", string="Odoo Name", readonly=True
    )
    odoo_partner_email = fields.Char(
        related="odoo_partner_id.email", string="Odoo Email", readonly=True
    )
    odoo_partner_phone = fields.Char(
        related="odoo_partner_id.phone", string="Odoo Phone", readonly=True
    )
    billcom_partner_id = fields.Char(
        string="Bill.com ID", readonly=True, help="Bill.com partner ID"
    )
    billcom_partner_name = fields.Char(string="Bill.com Name", readonly=True)
    billcom_partner_email = fields.Char(string="Bill.com Email", readonly=True)
    billcom_partner_phone = fields.Char(string="Bill.com Phone", readonly=True)

    # Multi-currency duplicate handling
    billcom_ids_json = fields.Text(
        string="Bill.com IDs JSON",
        help="JSON array of multiple Bill.com IDs with currencies for duplicate groups",
    )
    is_duplicate_group = fields.Boolean(
        default=False,
        help="True if this line represents multiple Bill.com records \
             (same vendor, different currencies)",
    )
    billcom_ids_count = fields.Integer(
        string="# Bill.com IDs",
        compute="_compute_billcom_ids_count",
        help="Number of Bill.com IDs in this group",
    )
    parent_partner_id = fields.Many2one(
        "res.partner",
        string="Parent Partner",
        help="Manually assign a parent partner for this duplicate group. "
        "Children will be created under this parent.",
    )

    confidence_level = fields.Selection(
        [
            ("high", "High (3/3)"),
            ("medium", "Medium (2/3)"),
            ("low", "Low (1/3)"),
            ("none", "No Match"),
        ],
        string="Confidence",
        readonly=True,
        help="Matching confidence based on email, phone, and name criteria",
    )
    match_score = fields.Integer(
        string="Score",
        readonly=True,
        help="Number of criteria matched (0-3)",
    )
    match_details = fields.Char(
        readonly=True,
        help="Details of what criteria matched",
    )
    action = fields.Selection(
        [
            ("link", "Link"),
            ("create", "Create in Odoo"),
            ("ignore", "Ignore"),
            ("review", "Review"),
        ],
        default="review",
        help="Action to take for this match",
    )
    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("linked", "Linked"),
            ("created", "Created in Odoo"),
            ("ignored", "Ignored"),
            ("error", "Error"),
        ],
        default="pending",
        readonly=True,
    )
    error_message = fields.Text(readonly=True)

    # Computed fields for color coding
    confidence_color = fields.Integer(compute="_compute_confidence_color")

    @api.depends("confidence_level")
    def _compute_confidence_color(self):
        """Compute color for tree view based on confidence level"""
        color_map = {
            "high": 10,  # Green
            "medium": 4,  # Blue
            "low": 2,  # Orange
            "none": 1,  # Red
        }
        for line in self:
            line.confidence_color = color_map.get(line.confidence_level, 0)

    @api.depends("billcom_ids_json", "is_duplicate_group")
    def _compute_billcom_ids_count(self):
        """Compute the number of Bill.com IDs in duplicate group"""
        for line in self:
            if line.is_duplicate_group and line.billcom_ids_json:
                try:
                    billcom_ids_data = json.loads(line.billcom_ids_json)
                    line.billcom_ids_count = len(billcom_ids_data)
                except Exception:
                    line.billcom_ids_count = 0
            else:
                line.billcom_ids_count = 1  # Single Bill.com ID

    def action_apply_link(self):  # noqa: C901
        for line in self:
            if line.is_duplicate_group and line.billcom_ids_json:
                line._link_duplicate_group_to_existing_partner()
                continue

            # Validate both partners are present
            if not line.billcom_partner_id:
                line.write(
                    {
                        "state": "error",
                        "error_message": "No Bill.com partner to link",
                    }
                )
                continue

            if not line.odoo_partner_id:
                line.write(
                    {
                        "state": "error",
                        "error_message": "No Odoo partner selected. "
                        "Please select a partner to link.",
                    }
                )
                continue

            # Check if the selected Odoo partner already has a Bill.com ID
            if line.odoo_partner_id.billcom_id:
                line.write(
                    {
                        "state": "error",
                        "error_message": _(
                            "This Odoo partner is already linked to Bill.com ID: %s. "
                            "Please unlink it first or choose a different partner."
                        )
                        % line.odoo_partner_id.billcom_id,
                    }
                )
                continue

            # Check if another Odoo partner is already linked to this Bill.com ID
            existing_link = self.env["res.partner"].search(
                [
                    ("billcom_id", "=", line.billcom_partner_id),
                    ("id", "!=", line.odoo_partner_id.id),
                ],
                limit=1,
            )
            if existing_link:
                line.write(
                    {
                        "state": "error",
                        "error_message": _(
                            f"Bill.com partner {line.billcom_partner_name} is already"
                            f" linked to Odoo partner: {existing_link.name} "
                            f"(ID: {existing_link.id}). Please unlink it first or "
                            f"choose a different Bill.com partner."
                        ),
                    }
                )
                continue

            try:
                # Determine partner type
                service = self.env["billcom.service"].sudo()
                partner_type = line.wizard_id.partner_type
                # Fetch complete partner data from Bill.com
                endpoint = (
                    f"vendors/{line.billcom_partner_id}"
                    if partner_type == "vendor"
                    else f"customers/{line.billcom_partner_id}"
                )

                billcom_data = service._make_request(endpoint, method="GET")
                _logger.info(
                    f"Fetched complete {partner_type} data from "
                    f"Bill.com for {line.odoo_partner_id.name}"
                )

                # Update ALL partner fields with Bill.com data
                vals = {
                    "name": billcom_data.get("name")
                    or billcom_data.get("companyName", line.odoo_partner_id.name),
                    "is_sync_to_billcom": True,
                    "billcom": line.billcom_partner_id,
                    "billcom_id": line.billcom_partner_id,
                    "email": billcom_data.get("email") or line.odoo_partner_id.email,
                    "phone": billcom_data.get("phone") or line.odoo_partner_id.phone,
                    "ref": billcom_data.get("accountNumber")
                    or line.odoo_partner_id.ref,
                    "vat": billcom_data.get("taxId") or line.odoo_partner_id.vat,
                    "active": not billcom_data.get("archived", False),
                    "last_sync_date": fields.Datetime.now(),
                    "company_type": (
                        "company"
                        if billcom_data.get("accountType") == "BUSINESS"
                        else "person"
                    ),
                }

                # Capture and set Bill.com currency
                bill_currency = billcom_data.get("billCurrency", "USD")
                currency = self.env["res.currency"].search(
                    [("name", "=", bill_currency)], limit=1
                )
                if currency:
                    vals["billcom_res_currency_id"] = currency.id

                # Set supplier or customer rank
                if partner_type == "vendor":
                    vals["supplier_rank"] = 1
                else:
                    vals["customer_rank"] = 1

                # Add short name as comment if exists
                if billcom_data.get("shortName"):
                    vals["comment"] = f"Short name: {billcom_data.get('shortName')}"

                # Map address - Bill.com API v3 uses different field names
                address_data = billcom_data.get("address") or billcom_data.get(
                    "billingAddress"
                )
                if address_data:
                    vals.update(
                        {
                            "street": address_data.get("line1")
                            or address_data.get("addressLine1"),
                            "street2": address_data.get("line2")
                            or address_data.get("addressLine2"),
                            "city": address_data.get("city"),
                            "zip": address_data.get("zipOrPostalCode")
                            or address_data.get("zip"),
                        }
                    )

                    # Map state
                    state_code = address_data.get(
                        "stateOrProvince"
                    ) or address_data.get("state")
                    if state_code:
                        state = self.env["res.country.state"].search(
                            [("code", "=", state_code)], limit=1
                        )
                        if state:
                            vals["state_id"] = state.id

                    # Map country
                    country_code = address_data.get("country")
                    if country_code:
                        country = self.env["res.country"].search(
                            [("code", "=", country_code)], limit=1
                        )
                        if country:
                            vals["country_id"] = country.id

                # Update Odoo partner with all Bill.com data
                line.odoo_partner_id.with_context(skip_billcom_sync=True).write(vals)
                _logger.info(
                    f"Updated Odoo partner {line.odoo_partner_id.name} with all Bill.com data"
                )

                # Sync bank account if paymentInformation exists
                payment_info = billcom_data.get("paymentInformation", {})
                if payment_info and payment_info.get("bankAccount"):
                    try:
                        service._sync_partner_bank_account(
                            line.odoo_partner_id, payment_info
                        )
                        _logger.info(
                            f"Synced bank account from Bill.com for {line.odoo_partner_id.name}"
                        )
                    except Exception as e:
                        _logger.warning(
                            f"Could not sync bank account from Bill.com: {e}"
                        )
                        # Don't fail the linking process if bank sync fails

                line.write({"state": "linked"})

                # Log success
                _logger.info(
                    f"Linked and synced partner {line.odoo_partner_id.name}"
                    f" (ID: {line.odoo_partner_id.id}) with Bill.com "
                    f"{line.billcom_partner_name} (ID: {line.billcom_partner_id})"
                )

                # Build sync details for message
                sync_details = []
                if vals.get("email"):
                    sync_details.append(f"Email: {vals['email']}")
                if vals.get("phone"):
                    sync_details.append(f"Phone: {vals['phone']}")
                if vals.get("street"):
                    sync_details.append(
                        f"Address: {vals['street']}, {vals.get('city', '')}"
                    )
                if payment_info and payment_info.get("bankAccount"):
                    sync_details.append("Bank Account: Synced")

                # Post message on partner for audit trail
                line.odoo_partner_id.message_post(
                    body=_(
                        "<p><strong>Bill.com Partner Linked & Synced</strong></p>"
                        "<ul>"
                        "<li>Bill.com Name: %(name)s</li>"
                        "<li>Bill.com ID: %(id)s</li>"
                        "<li>Confidence: %(confidence)s</li>"
                        "<li>Match Details: %(details)s</li>"
                        "<li>Synced Fields: %(fields)s</li>"
                        "<li>Linked via: Partner Matching Wizard</li>"
                        "</ul>"
                    )
                    % {
                        "name": line.billcom_partner_name,
                        "id": line.billcom_partner_id,
                        "confidence": dict(
                            line._fields["confidence_level"].selection
                        ).get(line.confidence_level),
                        "details": line.match_details,
                        "fields": (
                            ", ".join(sync_details)
                            if sync_details
                            else "All available fields"
                        ),
                    },
                    message_type="notification",
                    subtype_xmlid="mail.mt_note",
                )

            except Exception as e:
                error_msg = str(e)
                line.write({"state": "error", "error_message": error_msg})
                _logger.error(
                    f"Error linking partner {line.odoo_partner_id.name}: {error_msg}"
                )

    def _validate_parent(self, parent):
        if not parent:
            return None

        if parent.parent_id:
            _logger.warning(
                f"Partner '{parent.name}' (ID: {parent.id}) is a child "
                f"of '{parent.parent_id.name}'. Using '{parent.parent_id.name}' "
                f"(ID: {parent.parent_id.id}) as parent to prevent recursion."
            )
            return parent.parent_id

        return parent

    def _link_duplicate_group_to_existing_partner(self):
        self.ensure_one()

        if not self.odoo_partner_id:
            raise UserError(_("No Odoo partner selected for linking"))

        try:
            # Parse Bill.com IDs from JSON
            billcom_ids_data = json.loads(self.billcom_ids_json)
            if not billcom_ids_data:
                raise UserError(_("No Bill.com IDs found in duplicate group"))

            service = self.env["billcom.service"].sudo()
            partner_type = self.wizard_id.partner_type

            # Determine parent partner
            # Priority: parent_partner_id > odoo_partner_id
            if self.parent_partner_id:
                proposed_parent = self.parent_partner_id
                _logger.info(f"Manually assigned parent: {proposed_parent.name}")
            else:
                proposed_parent = self.odoo_partner_id
                _logger.info(f"Selected partner as parent: {proposed_parent.name}")

            # VALIDATE: Prevent recursion - if proposed parent is a child, use its parent
            parent_partner = self._validate_parent(proposed_parent)

            if not parent_partner:
                raise UserError(_("Invalid parent partner selected"))

            _logger.info(
                f"Linking duplicate group to validated parent {parent_partner.name}: "
                f"{len(billcom_ids_data)} Bill.com IDs"
            )

            # Track created vs existing children
            children_created = []
            children_existing = []
            currencies_summary = []

            # Create child partners for each Bill.com ID
            for bc_data in billcom_ids_data:
                bc_id = bc_data["id"]
                currency_code = bc_data.get("currency", "USD")

                # Get currency record
                currency = self.env["res.currency"].search(
                    [("name", "=", currency_code)], limit=1
                )
                if not currency:
                    _logger.warning(f"Currency {currency_code} not found, using USD")
                    currency = self.env.ref("base.USD")

                # Check if child already exists with this billcom_id
                existing_child = self.env["res.partner"].search(
                    [
                        "|",
                        ("billcom_id", "=", bc_id),
                        ("billcom", "=", bc_id),
                    ],
                    limit=1,
                )

                if existing_child:
                    # Child exists - update parent if needed
                    if existing_child.parent_id != parent_partner:
                        existing_child.write({"parent_id": parent_partner.id})
                        _logger.info(
                            f"Updated existing child {existing_child.name} to use "
                            f"parent {parent_partner.name}"
                        )
                    children_existing.append(existing_child.name)
                    currencies_summary.append(f"{currency_code} (existing)")
                    child_partner = existing_child
                else:
                    # Fetch complete data from Bill.com
                    endpoint = (
                        f"vendors/{bc_id}"
                        if partner_type == "vendor"
                        else f"customers/{bc_id}"
                    )
                    bc_complete_data = service._make_request(endpoint, method="GET")

                    # Create child partner
                    child_vals = {
                        "name": parent_partner.name,
                        "parent_id": parent_partner.id,
                        "billcom_res_currency_id": currency.id,
                        "is_sync_to_billcom": True,
                        "billcom": bc_id,
                        "billcom_id": bc_id,
                        "type": "contact",
                        "active": not bc_complete_data.get("archived", False),
                        "last_sync_date": fields.Datetime.now(),
                    }

                    if partner_type == "vendor":
                        child_vals["supplier_rank"] = 1
                    else:
                        child_vals["customer_rank"] = 1

                    child_partner = (
                        self.env["res.partner"]
                        .with_context(skip_billcom_sync=True)
                        .create(child_vals)
                    )
                    children_created.append(child_partner.name)
                    _logger.info(
                        f"Created child partner {child_partner.name} (ID: {child_partner.id})"
                    )

                # Create bank account in PARENT (not child)
                if not existing_child:
                    endpoint = (
                        f"vendors/{bc_id}"
                        if partner_type == "vendor"
                        else f"customers/{bc_id}"
                    )
                    bc_complete_data = service._make_request(endpoint, method="GET")
                    payment_info = bc_complete_data.get("paymentInformation", {})

                    if payment_info and payment_info.get("bankAccount"):
                        bank_data = payment_info["bankAccount"]

                        # Check if bank account already exists
                        existing_bank = self.env["res.partner.bank"].search(
                            [
                                ("partner_id", "=", parent_partner.id),
                                ("acc_number", "=", bank_data.get("accountNumber")),
                            ],
                            limit=1,
                        )

                        if not existing_bank:
                            bank_vals = {
                                "partner_id": parent_partner.id,
                                "acc_number": bank_data.get("accountNumber"),
                                "bank_name": bank_data.get("bankName"),
                                "currency_id": currency.id,
                                "billcom_vendor_id": child_partner.id,
                            }

                            if bank_data.get("routingNumber"):
                                bank_vals["aba_routing"] = bank_data["routingNumber"]

                            self.env["res.partner.bank"].create(bank_vals)
                            currencies_summary.append(f"{currency_code} (with bank)")
                            _logger.info(
                                f"Created bank account in parent for {currency_code}"
                            )
                        else:
                            currencies_summary.append(f"{currency_code} (bank exists)")
                    else:
                        currencies_summary.append(currency_code)

            # Update line state
            self.write({"state": "linked"})

            # Post message on parent for audit trail
            parent_partner.message_post(
                body=_(
                    "<p><strong>Bill.com Duplicate Group Linked (Parent-Child)</strong></p>"
                    "<ul>"
                    "<li>Parent: %(parent)s</li>"
                    "<li>Total Bill.com IDs: %(total)d</li>"
                    "<li>Children Created: %(created_count)d (%(created_names)s)</li>"
                    "<li>Children Existing: %(existing_count)d (%(existing_names)s)</li>"
                    "<li>Currencies: %(currencies)s</li>"
                    "<li>Partner Type: %(type)s</li>"
                    "<li>Linked via: Partner Matching Wizard</li>"
                    "</ul>"
                )
                % {
                    "parent": parent_partner.name,
                    "total": len(billcom_ids_data),
                    "created_count": len(children_created),
                    "created_names": (
                        ", ".join(children_created) if children_created else "none"
                    ),
                    "existing_count": len(children_existing),
                    "existing_names": (
                        ", ".join(children_existing) if children_existing else "none"
                    ),
                    "currencies": ", ".join(currencies_summary),
                    "type": partner_type.title(),
                },
                message_type="notification",
                subtype_xmlid="mail.mt_note",
            )

            _logger.info(
                f"Successfully linked duplicate group to {parent_partner.name}: "
                f"{len(children_created)} children created, {len(children_existing)}"
                f" already existed"
            )

        except Exception as e:
            error_msg = str(e)
            self.write({"state": "error", "error_message": error_msg})
            _logger.error(f"Error linking duplicate group: {error_msg}")

    def _create_partner_from_duplicate_group(self):  # noqa: C901
        """Create parent-child partner structure from Bill.com duplicate group

        Creates:
        - Parent partner (no billcom_id) with bank accounts
        - Child partners (each with billcom_id) under parent

        Example:
        Parent: "ABC Corp" (no billcom_id)
          ├─ res.partner.bank (USD account)
          ├─ res.partner.bank (EUR account)
          ├─ Child: "ABC Corp USD" (billcom_id=ven123)
          └─ Child: "ABC Corp EUR" (billcom_id=ven456)
        """
        self.ensure_one()

        try:
            # Parse Bill.com IDs from JSON
            billcom_ids_data = json.loads(self.billcom_ids_json)
            if not billcom_ids_data:
                raise UserError(_("No Bill.com IDs found in duplicate group"))

            service = self.env["billcom.service"].sudo()
            partner_type = self.wizard_id.partner_type

            # STEP 1: Check if any Bill.com ID already has a child partner
            # If so, use that child's parent (or promote child to parent)
            existing_child = None
            for bc_data in billcom_ids_data:
                bc_id = bc_data["id"]
                partner = self.env["res.partner"].search(
                    [
                        "|",
                        ("billcom_id", "=", bc_id),
                        ("billcom", "=", bc_id),
                    ],
                    limit=1,
                )

                if partner:
                    existing_child = partner
                    _logger.info(
                        f"Found existing child partner '{partner.name}' (ID: {partner.id}) "
                        f"with Bill.com ID {bc_id}"
                    )
                    break

            # STEP 2: Determine parent partner
            proposed_parent = None
            if self.parent_partner_id:
                # User manually assigned a parent
                proposed_parent = self.parent_partner_id
                _logger.info(f"Manually assigned parent: {proposed_parent.name}")
            elif existing_child and existing_child.parent_id:
                # Child already has a parent, use it
                proposed_parent = existing_child.parent_id
                _logger.info(f"Existing parent from child: {proposed_parent.name}")
            elif existing_child:
                # Child exists but has no parent - use child as parent
                proposed_parent = existing_child
                _logger.info(
                    f"Promoting existing child to parent: {proposed_parent.name}"
                )

            # VALIDATE: Prevent recursion
            if proposed_parent:
                parent_partner = self._validate_parent(proposed_parent)
                if not parent_partner:
                    raise UserError(_("Invalid parent partner"))
            else:
                # No parent assigned or exists - create new parent
                # Use first Bill.com record for parent name/data
                primary_data = billcom_ids_data[0]
                primary_id = primary_data["id"]

                endpoint = (
                    f"vendors/{primary_id}"
                    if partner_type == "vendor"
                    else f"customers/{primary_id}"
                )
                billcom_data = service._make_request(endpoint, method="GET")

                # Parent partner values (NO billcom_id)
                parent_vals = {
                    "name": billcom_data.get("name")
                    or billcom_data.get("companyName", "Unknown"),
                    "is_sync_to_billcom": False,  # Parent doesn't sync directly
                    "email": billcom_data.get("email"),
                    "phone": billcom_data.get("phone"),
                    "ref": billcom_data.get("accountNumber"),
                    "vat": billcom_data.get("taxId"),
                    "active": True,
                    "company_type": (
                        "company"
                        if billcom_data.get("accountType") == "BUSINESS"
                        else "person"
                    ),
                }

                # Set supplier or customer rank
                if partner_type == "vendor":
                    parent_vals["supplier_rank"] = 1
                else:
                    parent_vals["customer_rank"] = 1

                # Map address
                address_data = billcom_data.get("address") or billcom_data.get(
                    "billingAddress"
                )
                if address_data:
                    parent_vals.update(
                        {
                            "street": address_data.get("line1")
                            or address_data.get("addressLine1"),
                            "street2": address_data.get("line2")
                            or address_data.get("addressLine2"),
                            "city": address_data.get("city"),
                            "zip": address_data.get("zipOrPostalCode")
                            or address_data.get("zip"),
                        }
                    )

                    state_code = address_data.get(
                        "stateOrProvince"
                    ) or address_data.get("state")
                    if state_code:
                        state = self.env["res.country.state"].search(
                            [("code", "=", state_code)], limit=1
                        )
                        if state:
                            parent_vals["state_id"] = state.id

                    country_code = address_data.get("country")
                    if country_code:
                        country = self.env["res.country"].search(
                            [("code", "=", country_code)], limit=1
                        )
                        if country:
                            parent_vals["country_id"] = country.id

                # Create parent partner
                parent_partner = (
                    self.env["res.partner"]
                    .with_context(skip_billcom_sync=True)
                    .create(parent_vals)
                )
                _logger.info(
                    f"Created parent partner {parent_partner.name} (ID: {parent_partner.id})"
                )

            # STEP 3: Create child partners for each Bill.com ID
            children_created = []
            currencies_summary = []

            for bc_data in billcom_ids_data:
                bc_id = bc_data["id"]
                currency_code = bc_data.get("currency", "USD")

                # Get currency record
                currency = self.env["res.currency"].search(
                    [("name", "=", currency_code)], limit=1
                )
                if not currency:
                    _logger.warning(f"Currency {currency_code} not found, using USD")
                    currency = self.env.ref("base.USD")

                # Check if this child already exists
                existing = self.env["res.partner"].search(
                    [
                        "|",
                        ("billcom_id", "=", bc_id),
                        ("billcom", "=", bc_id),
                    ],
                    limit=1,
                )

                if existing:
                    # Update existing child's parent if needed
                    if existing.parent_id != parent_partner:
                        existing.write({"parent_id": parent_partner.id})
                        _logger.info(
                            f"Updated existing child {existing.name} to use "
                            f"parent {parent_partner.name}"
                        )
                    child_partner = existing
                else:
                    # Fetch complete data from Bill.com
                    endpoint = (
                        f"vendors/{bc_id}"
                        if partner_type == "vendor"
                        else f"customers/{bc_id}"
                    )
                    bc_complete_data = service._make_request(endpoint, method="GET")

                    # Child partner values
                    child_vals = {
                        "name": parent_partner.name,
                        "parent_id": parent_partner.id,
                        "billcom_res_currency_id": currency.id,
                        "is_sync_to_billcom": True,
                        "billcom": bc_id,
                        "billcom_id": bc_id,
                        "type": "contact",
                        "active": not bc_complete_data.get("archived", False),
                        "last_sync_date": fields.Datetime.now(),
                    }

                    if partner_type == "vendor":
                        child_vals["supplier_rank"] = 1
                    else:
                        child_vals["customer_rank"] = 1

                    # Create child partner
                    child_partner = (
                        self.env["res.partner"]
                        .with_context(skip_billcom_sync=True)
                        .create(child_vals)
                    )
                    children_created.append(child_partner)
                    _logger.info(
                        f"Created child partner {child_partner.name} (ID: {child_partner.id})"
                    )

                # STEP 4: Create bank account in PARENT (not child)
                payment_info = None
                if not existing:
                    endpoint = (
                        f"vendors/{bc_id}"
                        if partner_type == "vendor"
                        else f"customers/{bc_id}"
                    )
                    bc_complete_data = service._make_request(endpoint, method="GET")
                    payment_info = bc_complete_data.get("paymentInformation", {})

                if payment_info and payment_info.get("bankAccount"):
                    bank_data = payment_info["bankAccount"]

                    # Check if bank account already exists for this currency
                    existing_bank = self.env["res.partner.bank"].search(
                        [
                            ("partner_id", "=", parent_partner.id),
                            ("acc_number", "=", bank_data.get("accountNumber")),
                        ],
                        limit=1,
                    )

                    if not existing_bank:
                        bank_vals = {
                            "partner_id": parent_partner.id,
                            "acc_number": bank_data.get("accountNumber"),
                            "bank_name": bank_data.get("bankName"),
                            "currency_id": currency.id,
                            "billcom_vendor_id": child_partner.id,  # Link bank to child vendor
                        }

                        # Map routing number to ABA
                        if bank_data.get("routingNumber"):
                            bank_vals["aba_routing"] = bank_data["routingNumber"]

                        self.env["res.partner.bank"].create(bank_vals)
                        currencies_summary.append(f"{currency_code} (with bank)")
                        _logger.info(
                            f"Created bank account in parent for {currency_code}"
                        )
                    else:
                        currencies_summary.append(f"{currency_code} (bank exists)")
                else:
                    currencies_summary.append(currency_code)

            # Update line state
            self.write({"odoo_partner_id": parent_partner.id, "state": "created"})

            # Post message on parent for audit trail
            parent_partner.message_post(
                body=_(
                    "<p><strong>Parent-Child Structure Created from Bill.com"
                    " Duplicate Group</strong></p>"
                    "<ul>"
                    "<li>Parent: %(name)s (ID: %(id)d)</li>"
                    "<li>Children created: %(count)d</li>"
                    "<li>Currencies: %(currencies)s</li>"
                    "<li>Bill.com IDs: %(billcom_ids)s</li>"
                    "<li>Partner Type: %(type)s</li>"
                    "<li>Created via: Partner Matching Wizard</li>"
                    "</ul>"
                )
                % {
                    "name": parent_partner.name,
                    "id": parent_partner.id,
                    "count": len(children_created),
                    "currencies": ", ".join(currencies_summary),
                    "billcom_ids": ", ".join([bc["id"] for bc in billcom_ids_data]),
                    "type": partner_type.title(),
                },
                message_type="notification",
                subtype_xmlid="mail.mt_note",
            )

            _logger.info(
                f"Successfully created parent-child structure: "
                f"Parent: {parent_partner.name}, Children: {len(children_created)}, "
                f"Currencies: {len(currencies_summary)}"
            )

        except Exception as e:
            error_msg = str(e)
            self.write({"state": "error", "error_message": error_msg})
            _logger.error(
                f"Error creating parent-child from duplicate group: {error_msg}"
            )

    def action_apply_create(self):  # noqa: C901
        """Create new Odoo partner from Bill.com data

        Handles both single Bill.com records and duplicate groups (multiple
        Bill.com records with different currencies → one Odoo partner).
        """
        for line in self:
            # Handle duplicate group (multiple Bill.com IDs → one Odoo partner)
            if line.is_duplicate_group and line.billcom_ids_json:
                line._create_partner_from_duplicate_group()
                continue

            # Validate Bill.com partner is present
            if not line.billcom_partner_id:
                line.write(
                    {
                        "state": "error",
                        "error_message": "No Bill.com partner to create from",
                    }
                )
                continue

            # Check if partner already exists with this Bill.com ID
            existing_partner = self.env["res.partner"].search(
                [
                    "|",
                    ("billcom_id", "=", line.billcom_partner_id),
                    ("billcom", "=", line.billcom_partner_id),
                ],
                limit=1,
            )
            if existing_partner:
                line.write(
                    {
                        "state": "error",
                        "error_message": _(
                            f"A partner with Bill.com ID {line.billcom_partner_id} "
                            f"already exists in Odoo: {existing_partner.name} "
                            f"(ID: {existing_partner.id}). Use 'Link' action instead."
                        ),
                    }
                )
                continue

            try:
                # Determine partner type
                service = self.env["billcom.service"].sudo()
                partner_type = line.wizard_id.partner_type

                # Fetch complete partner data from Bill.com
                endpoint = (
                    f"vendors/{line.billcom_partner_id}"
                    if partner_type == "vendor"
                    else f"customers/{line.billcom_partner_id}"
                )

                billcom_data = service._make_request(endpoint, method="GET")
                _logger.info(
                    f"Fetched complete {partner_type} data from Bill.com for "
                    f"creating new partner: {billcom_data.get('name')}"
                )

                # Prepare partner values from Bill.com data
                vals = {
                    "name": billcom_data.get("name")
                    or billcom_data.get("companyName", "Unknown"),
                    "is_sync_to_billcom": True,
                    "billcom": line.billcom_partner_id,
                    "billcom_id": line.billcom_partner_id,
                    "email": billcom_data.get("email"),
                    "phone": billcom_data.get("phone"),
                    "ref": billcom_data.get("accountNumber"),
                    "vat": billcom_data.get("taxId"),
                    "active": not billcom_data.get("archived", False),
                    "last_sync_date": fields.Datetime.now(),
                    "company_type": (
                        "company"
                        if billcom_data.get("accountType") == "BUSINESS"
                        else "person"
                    ),
                }

                # Capture and set Bill.com currency
                bill_currency = billcom_data.get("billCurrency", "USD")
                currency = self.env["res.currency"].search(
                    [("name", "=", bill_currency)], limit=1
                )
                if currency:
                    vals["billcom_res_currency_id"] = currency.id

                # Set supplier or customer rank
                if partner_type == "vendor":
                    vals["supplier_rank"] = 1
                else:
                    vals["customer_rank"] = 1

                # Add short name as comment if exists
                if billcom_data.get("shortName"):
                    vals["comment"] = f"Short name: {billcom_data.get('shortName')}"

                # Map address - Bill.com API v3 uses different field names
                address_data = billcom_data.get("address") or billcom_data.get(
                    "billingAddress"
                )
                if address_data:
                    vals.update(
                        {
                            "street": address_data.get("line1")
                            or address_data.get("addressLine1"),
                            "street2": address_data.get("line2")
                            or address_data.get("addressLine2"),
                            "city": address_data.get("city"),
                            "zip": address_data.get("zipOrPostalCode")
                            or address_data.get("zip"),
                        }
                    )

                    # Map state
                    state_code = address_data.get(
                        "stateOrProvince"
                    ) or address_data.get("state")
                    if state_code:
                        state = self.env["res.country.state"].search(
                            [("code", "=", state_code)], limit=1
                        )
                        if state:
                            vals["state_id"] = state.id

                    # Map country
                    country_code = address_data.get("country")
                    if country_code:
                        country = self.env["res.country"].search(
                            [("code", "=", country_code)], limit=1
                        )
                        if country:
                            vals["country_id"] = country.id

                # Create new Odoo partner
                new_partner = (
                    self.env["res.partner"]
                    .with_context(skip_billcom_sync=True)
                    .create(vals)
                )
                _logger.info(
                    f"Created new Odoo partner {new_partner.name} (ID: {new_partner.id})"
                    f" from Bill.com {line.billcom_partner_name}"
                )

                # Update line with created partner
                line.write({"odoo_partner_id": new_partner.id, "state": "created"})

                # Sync bank account if paymentInformation exists
                payment_info = billcom_data.get("paymentInformation", {})
                if payment_info and payment_info.get("bankAccount"):
                    try:
                        service._sync_partner_bank_account(new_partner, payment_info)
                        _logger.info(
                            f"Synced bank account from Bill.com for {new_partner.name}"
                        )
                    except Exception as e:
                        _logger.warning(
                            f"Could not sync bank account from Bill.com: {e}"
                        )
                        # Don't fail the creation process if bank sync fails

                # Build sync details for message
                sync_details = []
                if vals.get("email"):
                    sync_details.append(f"Email: {vals['email']}")
                if vals.get("phone"):
                    sync_details.append(f"Phone: {vals['phone']}")
                if vals.get("street"):
                    sync_details.append(
                        f"Address: {vals['street']}, {vals.get('city', '')}"
                    )
                if payment_info and payment_info.get("bankAccount"):
                    sync_details.append("Bank Account: Synced")

                # Post message on partner for audit trail
                new_partner.message_post(
                    body=_(
                        "<p><strong>Partner Created from Bill.com</strong></p>"
                        "<ul>"
                        "<li>Bill.com Name: %(name)s</li>"
                        "<li>Bill.com ID: %(id)s</li>"
                        "<li>Partner Type: %(type)s</li>"
                        "<li>Synced Fields: %(fields)s</li>"
                        "<li>Created via: Partner Matching Wizard</li>"
                        "</ul>"
                    )
                    % {
                        "name": line.billcom_partner_name,
                        "id": line.billcom_partner_id,
                        "type": partner_type.title(),
                        "fields": (
                            ", ".join(sync_details)
                            if sync_details
                            else "All available fields"
                        ),
                    },
                    message_type="notification",
                    subtype_xmlid="mail.mt_note",
                )

                _logger.info(
                    f"Successfully created partner {new_partner.name} (ID: {new_partner.id}) "
                    f"from Bill.com {line.billcom_partner_name} (ID: {line.billcom_partner_id})"
                )

            except Exception as e:
                error_msg = str(e)
                line.write({"state": "error", "error_message": error_msg})
                _logger.error(
                    f"Error creating partner from Bill.com"
                    f" {line.billcom_partner_name}: {error_msg}"
                )

    def action_ignore(self):
        """Mark this match as ignored"""
        self.ensure_one()
        self.write({"action": "ignore", "state": "ignored"})

    def action_select_for_link(self):
        """Select this match for linking"""
        self.ensure_one()
        self.write({"action": "link"})

    def action_search_billcom(self):
        """Open search dialog to manually find Bill.com partner"""
        self.ensure_one()

        # This would open a new wizard for manual search
        # For now, we'll just show a message
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Manual Search"),
                "message": _(
                    "Manual search feature coming soon. "
                    "For now, please use the Bill.com sync wizard to create a new partner."
                ),
                "type": "info",
                "sticky": False,
            },
        }

    def action_unlink_partner(self):
        """Unlink Bill.com ID from Odoo partner (in case of error)"""
        self.ensure_one()

        if not self.odoo_partner_id.billcom_id:
            raise UserError(_("This partner is not linked to Bill.com"))

        old_billcom_id = self.odoo_partner_id.billcom_id

        self.odoo_partner_id.with_context(skip_billcom_sync=True).write(
            {
                "billcom_id": False,
                "billcom": False,
            }
        )

        self.write({"state": "pending", "error_message": False})

        # Post message on partner
        self.odoo_partner_id.message_post(
            body=_(
                "<p><strong>Bill.com Partner Unlinked</strong></p>"
                "<ul>"
                "<li>Previous Bill.com ID: %s</li>"
                "<li>Unlinked via: Partner Matching Wizard</li>"
                "</ul>"
            )
            % old_billcom_id,
            message_type="notification",
            subtype_xmlid="mail.mt_note",
        )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Success"),
                "message": _("Partner unlinked successfully"),
                "type": "success",
                "sticky": False,
            },
        }
