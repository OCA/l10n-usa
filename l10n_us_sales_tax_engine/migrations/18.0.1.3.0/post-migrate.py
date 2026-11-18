# Copyright 2026 Binhex - Edilio Escalona Almira.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Let branches read the nexus of their parent companies.

    The rule lives in a ``noupdate`` file, so an upgrade keeps the domain it
    had at install time. Its write, create and unlink checks move to
    ``us_tax_nexus_rule_company_write``, which the upgrade creates.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    rule = env.ref(
        "l10n_us_sales_tax_engine.rule_us_tax_nexus_company",
        raise_if_not_found=False,
    )
    if rule:
        rule.write(
            {
                "domain_force": "['|', ('company_id', '=', False), "
                "('company_id', 'parent_of', company_ids)]",
                "perm_read": True,
                "perm_write": False,
                "perm_create": False,
                "perm_unlink": False,
            }
        )
