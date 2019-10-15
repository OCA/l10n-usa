# Copyright 2018-2019 Eficent Business and IT Consulting Services S.L.
#   (http://www.eficent.com)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
import logging


_logger = logging.getLogger(__name__)

try:
    import taxjar
except ImportError:
    _logger.debug("`taxjar` Python library not installed.")


class TaxJarRequest(object):

    def __init__(self, api_url, api_token):
        self.taxjar = taxjar.Client(api_token, api_url)

    def get_product_tax_code(self):
        return self.taxjar.categories()

    def get_nexus_regions(self):
        return self.taxjar.nexus_regions()

    # TODO: Validate Nexus workflow consistency.
    def get_rate(self, lines, to_address, from_address):
        line_items = []
        for line in lines:
            rec = {
                'id': line.id,
                'unit_price': line.price_unit,
                'quantity': line.quantity
                if hasattr(line, 'quantity') else line.product_uom_qty,
                'discount': line.discount,
            }
            tax_code = line.product_id.product_tmpl_id.tax_code_id or \
                line.product_id.product_tmpl_id.categ_id.tax_code_id
            if tax_code:
                rec['product_tax_code'] = tax_code.code
            line_items.append(rec)

        body = {
            'from_country': from_address.state_id.country_id.code,
            'from_zip': from_address.zip,
            'from_state': from_address.state_id.code,
            'from_city': from_address.city,
            'from_street': from_address.street,
            'to_country':
                to_address.state_id.country_id.code
                if to_address.state_id else to_address.country_id.code,
            'to_zip': to_address.zip,
            'to_state': to_address.state_id.code or '',
            'to_city': to_address.city or '',
            'to_street': to_address.street or '',
            'shipping': 0.0,
            'line_items': line_items
        }
        # TODO: According with TaxJar support Our API will only return sales
        #       tax and the breakdown showing jurisdictions when the 'to'
        #       address is in one of your nexus locations.
        # if nexus.sourcing_type == 'origin':
        #     nexus_addresses = [{
        #         'id': nexus.name,
        #         'country': company.state_id.country_id.code,
        #         'state': company.state_id.code,
        #         'zip': company.zip,
        #         'city': company.city,
        #         'street': company.street,
        #     }]
        #     extend_body = {'nexus_addresses': nexus_addresses}
        #     body = {**body, **extend_body}
        # TODO: nexus_address should be some warehouse location in that state
        #  so, let's keep empty until we reach where to put that information
        #  https://support.taxjar.com/article/170-address-of-nexus-guidelines
        # elif nexus.sourcing_type == 'destination':
        #     nexus_addresses = [{
        #         'id': nexus.name,
        #         'country': partner.state_id.country_id.code,
        #         'state': partner.state_id.code,
        #         'zip': partner.zip,
        #         'city': partner.city,
        #         'street': partner.street,
        #     }]
        #     extend_body = {'nexus_addresses': nexus_addresses}
        #     body = {**body, **extend_body}

        response = self.taxjar.tax_for_order(body)

        return response
