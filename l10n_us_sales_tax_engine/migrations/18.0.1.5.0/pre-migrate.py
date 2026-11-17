# Copyright 2026 Binhex - Edilio Escalona Almira.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
"""Pre-migration for l10n_us_sales_tax_engine 18.0.1.5.0.

Creates the columns of the two stored computed fields of the US tax
fingerprint, us_tax_input_hash and us_tax_is_stale, before the ORM loads
the module. When the ORM has to create the column of a stored computed
field itself, it computes the field for every row of the table, which on
account_move means every journal entry and vendor bill. With the columns
already there nothing is computed at load time, and post-migrate.py
computes them only for the documents the engine can still recalculate.
"""

from odoo.tools.sql import column_exists, create_column

COLUMNS = {
    "sale_order": (("us_tax_input_hash", "varchar"), ("us_tax_is_stale", "boolean")),
    "account_move": (("us_tax_input_hash", "varchar"), ("us_tax_is_stale", "boolean")),
}


def migrate(cr, version):
    if not version:
        return
    for table, columns in COLUMNS.items():
        for name, sql_type in columns:
            if not column_exists(cr, table, name):
                create_column(cr, table, name, sql_type)
