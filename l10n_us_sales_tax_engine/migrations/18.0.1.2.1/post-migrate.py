# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

EXEMPTION_FIELDS = [
    "us_tax_exempt",
    "us_tax_exemption_code",
    "us_tax_exemption_number",
]


def migrate(cr, version):
    """Sync exemptions set before the fields were delegated.

    A post_init_hook would not reach these: Odoo calls it only for a new
    install, and on a new install no partner carries the field yet.

    Scoped to the exemption fields on purpose. ``_commercial_fields()`` also
    holds vat, company registry and the account properties, and an exemption
    fix has no business rewriting those on every contact.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    exempt = env["res.partner"].search(
        [("us_tax_exempt", "=", True), ("parent_id", "=", False)]
    )
    for partner in exempt:
        partner._commercial_sync_to_children(fields_to_sync=EXEMPTION_FIELDS)
    if exempt:
        _logger.info("US Tax: synced %s exempt customer(s) to contacts.", len(exempt))
