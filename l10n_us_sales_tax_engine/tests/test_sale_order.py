# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from .common import UsTaxBaseTest


class TestSaleOrderTax(UsTaxBaseTest):

    def test_calculate_tax_action(self):
        """manual 'Calculate US Tax' button on SO must not raise errors."""
        order = self.env['sale.order'].create({
            'partner_id': self.partner_fl.id,
            'partner_shipping_id': self.partner_fl.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': 2,
                'price_unit': 100.0,
            })],
        })
        # Should not raise
        try:
            order.action_calculate_us_tax()
        except Exception as exc:
            self.fail(f'action_calculate_us_tax raised unexpectedly: {exc}')

    def test_non_us_partner_skips_tax(self):
        """Non-US partner should be skipped by engine."""
        fr = self.env.ref('base.fr')
        partner_fr = self.env['res.partner'].create({
            'name': 'Test FR Partner',
            'country_id': fr.id,
        })
        order = self.env['sale.order'].create({
            'partner_id': partner_fr.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': 1,
                'price_unit': 50.0,
            })],
        })
        engine = self.env['us.tax.engine.service']
        result = engine.calculate_for_sale_order(order)
        self.assertIn(result.get('source', ''), ['skip_non_us', 'skip_no_address', 'disabled'])
