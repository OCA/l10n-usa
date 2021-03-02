# Copyright (C) 2017 Open Source Integrators
# Copyright (C) 2019 Brian McMaster
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE account_move_line aml
        SET is_1099 = v.is_1099,
            type_1099_id = v.type_1099_id,
            box_1099_misc_id = v.box_1099_misc_id
        FROM res_partner v
        WHERE aml.partner_id = v.id
        """,
    )
