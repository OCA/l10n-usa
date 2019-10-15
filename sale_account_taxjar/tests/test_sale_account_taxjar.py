# Copyright 2018-2019 Eficent Business and IT Consulting Services S.L.
# - (https://www.eficent.com)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
import logging
from os.path import dirname, join
from odoo.addons.account_taxjar.tests.utils import scrub_string
from odoo.addons.account_taxjar.tests.test_account_taxjar import \
    TestAccountTaxjar

from vcr import VCR

logging.getLogger("vcr").setLevel(logging.WARNING)

recorder = VCR(
    record_mode='once',
    cassette_library_dir=join(dirname(__file__), '../../account_taxjar/tests',
                              'fixtures/cassettes'),
    path_transformer=VCR.ensure_suffix('.yaml'),
    filter_headers=['Authorization'],
    decode_compressed_response=True,
)


class TestSaleAccountTaxjar(TestAccountTaxjar):

    def test_03_validate_on_update_taxjar_taxes(self):
        self.product_template.tax_code_id = \
            self.env['taxjar.category'].search([('code', '=', '31000')],
                                               limit=1).id
        so = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'partner_invoice_id': self.customer.id,
            'partner_shipping_id': self.customer.id,
            'warehouse_id': self.browse_ref('stock.warehouse0').id,
            'order_line': [(0, 0, {'name': self.product_product.name,
                                   'product_id': self.product_product.id,
                                   'product_uom_qty': 1,
                                   'product_uom': self.uom_unit.id,
                                   'price_unit': 200.0,
                                   })]})
        taxjar_nexus_sourcing = self.env['taxjar.nexus.sourcing'].search(
            [('name', 'ilike', self.customer.state_id.name)], limit=1
        )
        self.afp.taxjar_nexus_sourcing_id = \
            taxjar_nexus_sourcing.id
        # Get fiscal_position_id
        so.onchange_partner_shipping_id()
        # Confirm our standard sale order
        so.action_confirm()
        with recorder.use_cassette(
                path='test_03_validate_on_update_taxjar_taxes',
                before_record_response=scrub_string(
                    'OLD_ACCOUNT_LINE_ID',
                    str(so.order_line.id))
        ):
            so.prepare_taxes()
            self.assertEqual(so.amount_total, 215.8)

    def test_04_validate_on_update_zero_taxes(self):
        self.service_template.tax_code_id = self.env[
            'taxjar.category'].search([('code', '=', '19000')], limit=1).id
        so = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'partner_invoice_id': self.customer.id,
            'partner_shipping_id': self.customer.id,
            'warehouse_id': self.browse_ref('stock.warehouse0').id,
            'order_line': [(0, 0, {'name': self.service_product.name,
                                   'product_id': self.service_product.id,
                                   'product_uom_qty': 1,
                                   'product_uom': self.uom_unit.id,
                                   'price_unit': 50.0,
                                   })]})
        taxjar_nexus_sourcing = self.env['taxjar.nexus.sourcing'].search(
            [('name', 'ilike', self.customer.state_id.name)], limit=1)
        self.afp.taxjar_nexus_sourcing_id = \
            taxjar_nexus_sourcing.id
        # Get fiscal_position_id
        so.onchange_partner_shipping_id()
        with recorder.use_cassette(
                path='test_04_validate_on_update_zero_taxes',
                before_record_response=scrub_string(
                    'OLD_ACCOUNT_LINE_ID',
                    str(so.order_line.id))
        ):
            so.prepare_taxes()
            # Confirm our standard sale order
            so.action_confirm()
            self.assertEqual(so.amount_total, 50)
