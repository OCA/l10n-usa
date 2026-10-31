# Copyright 2026 Binhex - Edilio Escalona Almira.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo.tools import SQL
from odoo.tools.sql import column_exists, create_column


def pre_init_hook(env):
    """Create the document check unset so installing does not compute it.

    With the column already in place the ORM skips the compute over every
    existing sale order and journal entry: they keep the engine's behaviour.
    """
    for table in ("sale_order", "account_move"):
        if column_exists(env.cr, table, "us_tax_based_on_company"):
            continue
        create_column(
            env.cr,
            tablename=table,
            columnname="us_tax_based_on_company",
            columntype="boolean",
        )
        env.cr.execute(
            SQL(
                "UPDATE %s SET us_tax_based_on_company = false",
                SQL.identifier(table),
            )
        )
