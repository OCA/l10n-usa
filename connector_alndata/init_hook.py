# Copyright (C) 2019 Open Source Integrators
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, SUPERUSER_ID


def pre_init_hook(cr):

    env = api.Environment(cr, SUPERUSER_ID, {})
    fsm_location = env['ir.model'].search([('model', '=', 'fsm.location')])

    customer_id = env['ir.model.fields'].search_count(
        [('name', '=', 'customer_id'),
         ('ttype', '=', 'many2one'),
         ('relation', '=', 'res.partner'),
         ('model_id', '=', fsm_location.id)])

    if not customer_id:
        cr.execute("""ALTER TABLE "fsm_location" ADD "customer_id" INT;""")
        cr.execute("""UPDATE "fsm_location" SET customer_id = owner_id
        WHERE customer_id IS NULL;""")
        customer_id_vals = {
            'name': 'customer_id',
            'ttype': 'many2one',
            'relation': 'res.partner',
            'field_description': 'Billed Customer',
            'required': False,
            'stored': True,
            'model_id': fsm_location.id,
            'on_delete': 'restrict',
            'track_visibility': 'onchange',
            'state': 'base',
        }
        env['ir.model.fields'].create(customer_id_vals)
