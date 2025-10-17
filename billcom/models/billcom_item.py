# Copyright 2025 Binhex.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .billcom_document import parse_billcom_datetime

_logger = logging.getLogger(__name__)


class BillcomItem(models.Model):
    _name = "billcom.item"
    _description = "Bill.com Item (Classifications)"
    _inherit = ["billcom.abstract.model", "mail.thread", "mail.activity.mixin"]

    # Item type - focusing on SALES_TAX for tax mapping
    type = fields.Selection(
        [
            ("UNDEFINED", "Undefined"),
            ("UNKNOWN", "Unknown"),
            ("SERVICE", "Service"),
            ("INVENTORY", "Inventory"),
            ("NON_INVENTORY", "Non-Inventory"),
            ("PAYMENT", "Payment"),
            ("DISCOUNT", "Discount"),
            ("SALES_TAX", "Sales Tax"),
            ("SUBTOTAL", "Subtotal"),
            ("OTHER_CHARGE", "Other Charge"),
            ("INVENTORY_ASSEMBLY", "Inventory Assembly"),
            ("GROUP", "Group"),
            ("SALES_TAX_GROUP", "Sales Tax Group"),
            ("FIXED_ASSET", "Fixed Asset"),
            ("CATEGORY", "Category"),
            ("EXPENSE", "Expense"),
        ],
        string="Item Type",
        required=True,
        default="SALES_TAX",
        help="Type of item in Bill.com. SALES_TAX is used for tax mapping.",
    )

    short_name = fields.Char(help="Item short name in Bill.com")

    name = fields.Char(
        string="Item Name",
        required=True,
        help="Item name in Bill.com (must be >= 1 character)",
    )

    description = fields.Text(help="Item description")

    archived = fields.Boolean(
        default=False,
        help="Set as true if the item is archived in Bill.com",
    )

    parent_id = fields.Many2one(
        "billcom.item",
        string="Parent Item",
        help="Parent item if this item is a child object",
    )

    price = fields.Float(help="Item price")

    purchase_cost = fields.Float(help="Item purchase cost in accounting system")

    purchase_description = fields.Text(
        help="Item description when used for bills/purchases",
    )

    taxable = fields.Boolean(help="Set as true if item is taxable")

    percentage = fields.Float(
        string="Tax Percentage",
        digits=(16, 4),
        help="Tax percentage for SALES_TAX, DISCOUNT, or OTHER_CHARGE types",
    )

    # Odoo tax mapping (inverse relation - taxes reference items)
    tax_ids = fields.One2many(
        "account.tax",
        "billcom_item_id",
        string="Linked Odoo Taxes",
        help="Odoo taxes that use this Bill.com item",
        readonly=True,
    )

    # Chart of accounts references
    chart_of_account_id = fields.Char(
        string="Chart of Account ID",
        help="Bill.com chart of accounts ID (begins with 0ca)",
    )

    expense_chart_of_account_id = fields.Char(
        string="Expense Chart of Account ID",
        help="Bill.com expense chart of accounts ID (begins with 0ca)",
    )

    # Timestamps from Bill.com
    created_time = fields.Datetime(readonly=True, help="Created date/time in Bill.com")

    updated_time = fields.Datetime(readonly=True, help="Updated date/time in Bill.com")

    def button_sync_to_billcom(self):
        """Sync item to Bill.com"""
        self.ensure_one()
        if not self.is_sync_to_billcom:
            return False

        try:
            service = self.env["billcom.service"]
            return service.sync_item(self)
        except Exception as e:
            _logger.error("Error syncing item %s to Bill.com: %s", self.name, str(e))
            raise UserError(_("Error syncing to Bill.com: %s") % str(e)) from e

    def _prepare_item_data(self):
        """Prepare item data for Bill.com API"""
        self.ensure_one()

        data = {
            "type": self.type,
            "name": self.name or "Tax Item",
        }

        # Optional fields
        if self.short_name:
            data["shortName"] = self.short_name
        if self.description:
            data["description"] = self.description
        if self.parent_id and self.parent_id.billcom_id:
            data["parentId"] = self.parent_id.billcom_id
        if self.price:
            data["price"] = self.price
        if self.purchase_cost:
            data["purchaseCost"] = self.purchase_cost
        if self.purchase_description:
            data["purchaseDescription"] = self.purchase_description
        if self.chart_of_account_id:
            data["chartOfAccountId"] = self.chart_of_account_id
        if self.expense_chart_of_account_id:
            data["expenseChartOfAccountId"] = self.expense_chart_of_account_id

        # Tax-specific fields
        if self.type in ["SALES_TAX", "DISCOUNT", "OTHER_CHARGE"]:
            if self.percentage:
                data["percentage"] = self.percentage
        if self.taxable is not False:  # Include if explicitly set
            data["taxable"] = self.taxable

        return data

    @api.model
    def sync_from_odoo_taxes(self):
        """Sync all Odoo taxes to Bill.com as SALES_TAX items

        This creates Bill.com items for Odoo taxes that don't have a mapping yet.
        """
        # Get all active taxes
        taxes = self.env["account.tax"].search(
            [("active", "=", True), ("type_tax_use", "in", ["sale", "purchase"])]
        )

        synced_count = 0
        error_count = 0

        for tax in taxes:
            # Check if already mapped
            if tax.billcom_item_id:
                _logger.info(
                    "Tax %s already mapped to Bill.com item %s",
                    tax.name,
                    tax.billcom_item_id.billcom_id,
                )
                continue

            # Create new item for this tax
            try:
                item_vals = {
                    "name": tax.name,
                    "type": "SALES_TAX",
                    "description": tax.description or tax.name,
                    "percentage": tax.amount,
                    "taxable": False,  # Tax items themselves are not taxable
                    "is_sync_to_billcom": True,
                }

                item = self.create(item_vals)
                # Sync to Bill.com
                item.button_sync_to_billcom()

                # Link tax to item
                tax.write({"billcom_item_id": item.id})

                synced_count += 1
                _logger.info("Created and synced Bill.com item for tax %s", tax.name)
            except Exception as e:
                error_count += 1
                _logger.error(
                    "Failed to create/sync Bill.com item for tax %s: %s",
                    tax.name,
                    str(e),
                )

        return {
            "synced": synced_count,
            "errors": error_count,
            "total": len(taxes),
        }

    @api.model
    def get_item_for_tax(self, tax):
        """Get Bill.com item ID for an Odoo tax

        Args:
            tax: account.tax record

        Returns:
            str: Bill.com item ID or False
        """
        if not tax or not tax.billcom_item_id:
            return False

        return tax.billcom_item_id.billcom_id or False

    @api.model
    def sync_items_from_billcom(self, item_type=None):  # noqa: C901
        """Import/update items from Bill.com API

        Args:
            item_type (str, optional): Filter by item type (e.g., 'SALES_TAX')

        Returns:
            dict: Statistics about the sync operation
        """
        try:
            _logger.info(
                "Starting items sync from Bill.com (type: %s)", item_type or "all"
            )

            service = self.env["billcom.service"]
            items_data = service.get_items(item_type=item_type)

            created = 0
            updated = 0
            errors = 0

            for item_data in items_data:
                billcom_id = None
                try:
                    billcom_id = item_data.get("id")
                    if not billcom_id:
                        _logger.warning("Item without ID, skipping")
                        errors += 1
                        continue

                    # Check if item already exists
                    existing = self.search([("billcom_id", "=", billcom_id)], limit=1)

                    # Prepare values from Bill.com data
                    vals = {
                        "billcom_id": billcom_id,
                        "billcom": billcom_id,
                        "name": item_data.get("name", "Unknown Item"),
                        "type": item_data.get("type", "UNKNOWN"),
                        "billcom_sync_status": "synced",
                        "last_sync_date": fields.Datetime.now(),
                    }

                    # Optional fields
                    if item_data.get("shortName"):
                        vals["short_name"] = item_data.get("shortName")
                    if item_data.get("description"):
                        vals["description"] = item_data.get("description")
                    if item_data.get("percentage") is not None:
                        vals["percentage"] = item_data.get("percentage")
                    if item_data.get("price") is not None:
                        vals["price"] = item_data.get("price")
                    if item_data.get("purchaseCost") is not None:
                        vals["purchase_cost"] = item_data.get("purchaseCost")
                    if item_data.get("purchaseDescription"):
                        vals["purchase_description"] = item_data.get(
                            "purchaseDescription"
                        )
                    if item_data.get("taxable") is not None:
                        vals["taxable"] = item_data.get("taxable")
                    if item_data.get("chartOfAccountId"):
                        vals["chart_of_account_id"] = item_data.get("chartOfAccountId")
                    if item_data.get("expenseChartOfAccountId"):
                        vals["expense_chart_of_account_id"] = item_data.get(
                            "expenseChartOfAccountId"
                        )
                    if item_data.get("parentId"):
                        # Try to find parent item
                        parent = self.search(
                            [("billcom_id", "=", item_data.get("parentId"))], limit=1
                        )
                        if parent:
                            vals["parent_id"] = parent.id
                    if item_data.get("isActive") is not None:
                        vals["archived"] = not item_data.get("isActive")

                    # Parse datetime fields from ISO format
                    if item_data.get("createdTime"):
                        created_dt = parse_billcom_datetime(
                            item_data.get("createdTime")
                        )
                        if created_dt:
                            vals["created_time"] = created_dt

                    if item_data.get("updatedTime"):
                        updated_dt = parse_billcom_datetime(
                            item_data.get("updatedTime")
                        )
                        if updated_dt:
                            vals["updated_time"] = updated_dt

                    if existing:
                        existing.write(vals)
                        item_record = existing
                        updated += 1
                        _logger.info(
                            "Updated item: %s (ID: %s)", vals["name"], billcom_id
                        )
                    else:
                        item_record = self.create(vals)
                        created += 1
                        _logger.info(
                            "Created item: %s (ID: %s)", vals["name"], billcom_id
                        )

                    # Try to auto-map SALES_TAX items to Odoo taxes by percentage
                    if vals.get("type") == "SALES_TAX" and vals.get("percentage"):
                        # Search for matching tax by percentage
                        matching_tax = self.env["account.tax"].search(
                            [
                                ("amount", "=", vals["percentage"]),
                                ("type_tax_use", "in", ["sale", "purchase"]),
                                ("active", "=", True),
                                ("billcom_item_id", "=", False),  # Not already mapped
                            ],
                            limit=1,
                        )
                        if matching_tax:
                            matching_tax.write({"billcom_item_id": item_record.id})
                            _logger.info(
                                "Auto-mapped Bill.com item %s to Odoo tax %s",
                                vals["name"],
                                matching_tax.name,
                            )

                except Exception as e:
                    errors += 1
                    _logger.error(
                        "Error syncing item %s: %s", billcom_id or "unknown", str(e)
                    )

            _logger.info(
                "Items sync complete: %d created, %d updated, %d errors",
                created,
                updated,
                errors,
            )
            return {
                "created": created,
                "updated": updated,
                "errors": errors,
                "synced": created + updated,
                "total": len(items_data),
            }

        except Exception as e:
            _logger.error("Failed to sync items from Bill.com: %s", str(e))
            raise
