# Copyright (C) 2019 Open Source Integrators
# Copyright (C) 2019 Serpent Consulting Services Pvt. Ltd.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

import threading
import logging
import requests
import json
import base64

from odoo import api, fields, models, _, sql_db
from odoo.exceptions import RedirectWarning

_logger = logging.getLogger(__name__)

us_timezone = {
    'M': 'US/Mountain',
    'C': 'US/Central',
    'E': 'US/Eastern',
    'P': 'US/Pacific',
    'H': 'US/Hawaii',
}


class Lead(models.Model):
    _inherit = "crm.lead"

    lastdate_changed = fields.Datetime('LastDateChanged')
    industry_id = fields.Many2one('res.partner.industry', 'Market')
    lead_type = fields.Selection(
        [('owner', 'Owner'),
         ('management_company', 'Management Company'),
         ('contact', 'Contact'),
         ('new_construction', 'New Constructions')],
        'Lead Type')

    def aln_auth_login(self, data_key='', data_params=None):
        """Aln Connector.
        This method is used to connect with ALN and fetch the data.
        """
        config_obj = self.env['ir.config_parameter']
        url = config_obj.get_param('alndata.api.url')
        api_key = config_obj.get_param('alndata.api.key')
        full_content = []

        url = url + data_key
        count = 0
        flag = True
        params = {
            'apikey': api_key,
            'Accept': 'application/json',
        }
        _logger.info('ALN Data Connector Data Key: %s', data_key)
        if not data_params:
            data_params = {}
        params.update(data_params)

        # use count to fetch all data related filter by multiple request
        while flag:
            try:
                if count > 0:
                    params.update({'$skip': count})
                response = requests.get(url, params=params)
                response.raise_for_status()
            except Exception as e:
                _logger.error('%s', e)
                break
            content = response.content.decode('utf8')
            if content:
                content = json.loads(content).get('value')
                if len(content or []) > 0:
                    count += len(content)
                    full_content += content
                else:
                    flag = False
                    count = 0
        _logger.info('ALN Data Connector. Number of records: %s',
                     len(full_content))
        return full_content or []

    def remove_data(self, model, datas, origin=''):
        """Removed Data.
        This method is used to removed data from odoo database.
        which deleted from ALN Data.
        """
        obj = self.env[model]
        removed_ids = []
        rem = obj
        domain = []
        if model == 'res.partner':
            domain += [('partner_type', '=', origin)]
        elif origin and model == 'crm.lead':
            domain += [('lead_type', '=', origin)]
        for rec in obj.search(domain):
            if model == 'crm.lead' and rec.referred not in datas:
                removed_ids.append(rec.id)
                rem += rec
            elif model in ['res.partner', 'fsm.location'] and \
                    rec.ref not in datas:
                removed_ids.append(rec.id)
                rem += rec
        rem.write({'active': False})
        return removed_ids

    def get_state(self, obj, state_code):
        """State.
        This method is used to search state from state code.
        """
        return obj.search([('code', '=', state_code)], limit=1)

    def get_market(self, obj, market):
        """Market/Submarket.
        This method is used to search market or submarket base on name.
        """
        ctx = self.env.context
        domain = [('name', '=', market)]

        if ctx.get('search_archived'):
            domain += ['|', ('active', '=', True), ('active', '=', False)]
        return obj.search(domain, limit=1)

    @api.model
    def _prepare_industry_values(self, industry=None, origin='market'):
        if not industry:
            return {}
        marketID = industry.get('MarketId')
        values = {
            'name': marketID,
            'ref': marketID,  # We would not miss track to ALN ref
            'full_name': industry.get('MarketDescription'),
        }
        # prepare dataset for submarket
        if origin == 'submarket':
            values.update({
                'name': industry.get('SubMarketDescription'),
                'ref': industry.get('SubmarketId'),
            })
        return values

    @api.model
    def sync_market_data(self):
        """Synchronize Market Data.
        This method is used to sync market data.
        """
        industry_obj = self.env['res.partner.industry']
        market_ids = []
        updated_market_ids = []
        markets = self.aln_auth_login('Markets')
        for market in markets:
            available_market = self.with_context(
                search_archived=True).get_market(
                industry_obj, market.get('MarketId'))
            market_vals = self._prepare_industry_values(market)
            if available_market:
                if not available_market.active:
                    market_vals.update({'active': True})
                available_market.write(market_vals)
                updated_market_ids.append(available_market.id)
            else:
                market = industry_obj.create(market_vals)
                market_ids.append(market.id)
        _logger.info('ALN Data Connector.Created Market Ids : %s', market_ids)
        _logger.info('ALN Data Connector.Updated Market Ids : %s',
                     updated_market_ids)

    @api.model
    def sync_submarket_data(self):
        """Synchronize Submarket Data.
        This method is used to sync submarket data.
        """
        industry_obj = self.env['res.partner.industry']
        submarket_ids = []
        updated_submarket_ids = []
        for submarket in self.aln_auth_login('Submarkets'):
            available_submarket = self.with_context(
                search_archived=True).get_market(
                industry_obj, submarket.get('SubMarketDescription'))
            market_id = self.get_market(industry_obj,
                                        submarket.get('Market'))
            submarket_vals = self._prepare_industry_values(
                submarket, 'submarket')
            if market_id:
                submarket_vals.update({
                    'parent_id': market_id.id})
            if not available_submarket:
                submarket = industry_obj.create(submarket_vals)
                submarket_ids.append(submarket.id)
            else:
                if not available_submarket.active:
                    submarket_vals.update({'active': True})
                available_submarket.write(submarket_vals)
                updated_submarket_ids.append(available_submarket.id)
        _logger.info(
            'ALN Data Connector.Created SubMarket Ids : %s', submarket_ids)
        _logger.info('ALN Data Connector.Updated SubMarket Ids : %s',
                     updated_submarket_ids)

    @api.model
    def sync_status_code_data(self):
        """Synchronize Status Codes Data.
        This method is used to sync status code data.
        """
        status_obj = self.env['fsm.stage']
        stage_ids = []
        for state in self.aln_auth_login('StatusCodes'):
            available_state = self.get_market(status_obj,
                                              state.get('StatusDescription'))
            if not available_state:
                state_vals = {
                    'name': state.get('StatusDescription'),
                    'stage_type': 'location',
                    'sequence': state.get('Status'),
                }
                state = status_obj.create(state_vals)
                stage_ids.append(state.id)
        _logger.info(
            'ALN Data Connector.Created FSM Stage Ids : %s', stage_ids)

    @api.model
    def get_title(self, obj, title):
        """Get Title.
        This method is used to get title from odoo database
        if it is not exist then create a title.
        """
        title_id = obj.search([('name', '=', title)], limit=1)
        if not title_id:
            title_id = obj.create({'name': title})
        return title_id.id

    def sync_owner_contact_data(self, origin=''):
        """Synchronize Owner, Contact, Management Companies and
        New Constructions Data.
        This method is used to synchronize owner, contact,
        management companies and New Constructions Data.
        The origin parameter will differentiate the data.
        Using origin prepared values for owner, contact
        management companies data, new construction.
        """
        config_obj = self.env['ir.config_parameter']
        lead_obj = self.env['crm.lead']
        partner_obj = self.env['res.partner']
        industry_obj = self.env['res.partner.industry']
        state_obj = self.env['res.country.state']
        res_partner_title_obj = self.env['res.partner.title']
        partner_ids = []
        lead_ids = []
        contact_ids = []
        owner_ids = []
        construction_ids = []
        updated_partner_ids = []
        updated_lead_ids = []
        updated_contact_ids = []
        updated_owner_ids = []
        updated_construction_ids = []
        rowversion_list = []
        last_update_date = []
        params = {}
        removed_lead = []
        removed_partner = []
        # Get list for new partners for individual type
        new_owner_partner_list = []
        new_manage_partner_list = []
        new_contact_partner_list = []
        new_construction_partner_list = []

        if not origin:
            management_company_key = config_obj.get_param(
                'alndata.managementcompanies.rowversion')
            params.update({'$expand': 'Addresses,PhoneNumbers'})
            if management_company_key != '0':
                params.update(
                    {'$filter': 'RowVersion lt ' + management_company_key,
                     '$orderby': 'RowVersion'})
                old_manage_company = self.aln_auth_login(
                    'ManagementCompanies', params)
                company_id_ref = [dat.get('ManagementCompanyEntityId')
                                  for dat in old_manage_company]
                removed_lead = self.remove_data(
                    'crm.lead', company_id_ref, 'management_company')
                removed_partner = self.remove_data(
                    'res.partner', company_id_ref, 'management_company')
                params.update(
                    {'$filter': 'RowVersion gt ' + management_company_key,
                     '$orderby': 'RowVersion'})
            datas = self.aln_auth_login(
                'ManagementCompanies', params)
        elif origin == 'owner':
            datas = self.aln_auth_login('Owners')
            old_owner = [owner.get('OwnerId') for owner in datas]
            removed_lead = self.remove_data('crm.lead', old_owner, 'owner')
        elif origin == 'new_construction':
            construction_key = config_obj.get_param(
                'alndata.newconstructions.rowversion')
            if construction_key != '0':
                params.update(
                    {'$filter': "LastDateNewConstructionChanged lt datetime'" +
                                construction_key + "'",
                     '$orderby': "LastDateNewConstructionChanged"})
                old_construction = self.aln_auth_login(
                    'NewConstructions', params)
                constructions = [dat.get('NewConstructionId')
                                 for dat in old_construction]
                removed_lead = self.remove_data(
                    'crm.lead', constructions, 'new_construction')
                params.update(
                    {'$filter': "LastDateNewConstructionChanged gt datetime'" +
                                construction_key + "'",
                     '$orderby': "LastDateNewConstructionChanged"})
            datas = self.aln_auth_login('NewConstructions', params)
        else:
            contact_key = config_obj.get_param('alndata.contacts.rowversion')
            params.update({'$expand': 'Addresses,PhoneNumbers,JobCategories'})
            if contact_key != '0':
                params.update({'$filter': 'RowVersion lt ' + contact_key,
                               '$orderby': 'RowVersion'})
                old_contacts = self.aln_auth_login('Contacts', params)
                contacts = [cont.get('ContactId') for cont in old_contacts]
                removed_lead = self.remove_data(
                    'crm.lead', contacts, 'contact')
                params.update({'$filter': 'RowVersion gt ' + contact_key,
                               '$orderby': 'RowVersion'})
            datas = self.aln_auth_login('Contacts', params)

        for data in datas:
            obj = lead_obj
            name = data.get('ManagementCompanyName')
            rowversion = int(data.get('RowVersion', 0))
            rowversion_list.append(rowversion)
            last_changed = data.get('ManagementCompanyLastDateChanged')
            referred = data.get('ManagementCompanyEntityId')
            lead_type = 'management_company'
            # Prepare vals
            lead_vals = {
                'name': name,
            }
            # Prepare vals based on origin
            if origin == 'owner':
                name = data.get('OwnerName')
                lead_type = 'owner'
                last_changed = False
                referred = data.get('OwnerId')
                # Get address
                address = data.get('OwnerAddress', '')
                address_lst = address and address.split('\r\n') or []
                street = city = state_code = owner_zip = ''
                if len(address_lst) > 1:
                    street = address_lst[0]
                    city_state = address_lst[1].split(',')
                    if len(city_state) > 1:
                        city = city_state[0]
                        state_zip = (city_state[1].strip()).split(' ')
                        if len(state_zip) > 1:
                            state_code = state_zip[0]
                            owner_zip = state_zip[1]
                state = self.get_state(state_obj, state_code)
                # Prepare/update owner vals
                lead_vals.update({
                    'street': street,
                    'city': city,
                    'state_id': state.id,
                    'zip': owner_zip,
                    'country_id': state.country_id.id,
                    'phone': data.get('OwnerPhone'),
                    'contact_name': data.get('OwnerName'),
                    'name': name,
                })
            elif origin == 'contact':
                lead_type = 'contact'
                name = data.get('ContactName')
                last_changed = data.get('ContactLastDateChanged')
                referred = data.get('ContactId')

                lead = lead_obj.search([
                    ('referred', '=', data.get('AssociatedEntity'))], limit=1)
                partner_name = lead and lead.name or ''
                function = ''
                for job in data.get('JobCategories'):
                    function += job.get('JobCategoryDescription') + ','
                # Get Title
                title = False
                if data.get('ContactTitle', False):
                    title = self.get_title(res_partner_title_obj,
                                           data.get('ContactTitle'))
                # Prepare/update contact vals
                lead_vals.update({
                    'email_from': data.get('ContactEMail'),
                    'partner_name': partner_name,
                    'contact_name': data.get('ContactName'),
                    'title': title,
                    'function': function[:-1],
                    'name': name,
                })
            elif origin == 'new_construction':
                lead_type = "new_construction"
                # Name = company name + project name
                if data.get('Company', False):
                    name = str(data.get('Company')) + ' ' + str(data.get('ProjectName'))
                else:
                    name = data.get('ProjectName')
                referred = data.get('NewConstructionId')
                last_changed = data.get('LastDateNewConstructionChanged')
                if last_changed:
                    last_update_date.append(last_changed)

                state = self.get_state(state_obj, data.get('ProjectState'))
                description = ''
                if data.get('StartDate'):
                    description += "Start Date : " + data.get('StartDate')
                if data.get('LeaseDate'):
                    description += "\n" + "Lease Date : " + \
                                   data.get('LeaseDate')
                if data.get('OccupancyDate'):
                    description += "\n" + "Occupancy Date : " + \
                                   data.get('OccupancyDate')
                if data.get('CompletionDate'):
                    description += "\n" + "Completion Date : " + \
                                   data.get('CompletionDate')
                if data.get('Progress'):
                    description += "\n" + "Progress : " + data.get('Progress')
                if data.get('Market'):
                    description += "\n" + "Market : " + data.get('Market')
                # Prepare/update contact new construction
                lead_vals.update({
                    'street': data.get('ProjectAddress'),
                    'city': data.get('ProjectCity'),
                    'state_id': state.id,
                    'country_id': state.country_id.id,
                    'zip': data.get('ProjectZIP'),
                    'partner_name': data.get('Company'),
                    'description': description,
                    'num_unit': data.get('NumberOfUnits', False),
                    'name': name,
                })

            domain = [('name', '=', name)]
            if data.get('ManagementCompanyParentId'):
                obj = partner_obj
                domain += [('partner_type', '=', 'management_company'),
                           ('ref', '=', referred)]
            else:
                domain += [('lead_type', '=', lead_type),
                           ('referred', '=', referred)]
            # Prepare/update vals for Address
            if data.get('Addresses', False):
                address = data['Addresses'][0]
                state = self.get_state(state_obj,
                                       address.get('AddressState'))
                country_id = state and state.country_id.id or 0
                lead_vals.update(
                    {
                        'street': address.get('AddressLine1'),
                        'street2': address.get('AddressLine2'),
                        'city': address.get('AddressCity'),
                        'state_id': state.id,
                        'zip': address.get('AddressZIP'),
                        'country_id': country_id,
                        'address_type': address.get('AddressType'),
                    })
            # Prepare/update vals for Management company
            if data.get('ManagementCompanyEntityId'):
                # Get Market
                if data.get('ManagementCompanyMarket'):
                    market = industry_obj.search([('name', '=', data.get('ManagementCompanyMarket'))], limit=1)
                lead_vals.update(
                    {
                        'ref': data.get('ManagementCompanyEntityId'),
                        'partner_type': 'management_company',
                        'website': data.get('ManagementCompanyWebSite', False),
                        'industry_id': market and market.id or False,
                    })
            else:
                lead_vals.update(
                    {
                        'lead_type': lead_type,
                        'lastdate_changed': last_changed,
                        'referred': referred,
                    })
            if data.get('PhoneNumbers', False):
                numbers = data['PhoneNumbers']
                for num in numbers:
                    if num.get('IsPrimary') == 'Y':
                        lead_vals.update({
                            'phone': num.get('Number')
                        })
                    if (num.get('PhoneNumberType') == "Fax Number" and
                            data.get('ManagementCompanyParentId', False)):
                        lead_vals.update({
                            'fax': num.get('Number')
                        })

            domain += ['|', ('active', '=', True), ('active', '=', False)]
            lead = obj.search(domain)

            # If crm.lead obj remove few elements from dict
            if obj == lead_obj:
                lead_vals.pop('ref', False)
                lead_vals.pop('num_unit', False)
                lead_vals.pop('partner_type', False)
                lead_vals.pop('address_type', False)
                lead_vals.update({'referred': referred})

            if lead:
                # If lead prepare counts for updated records
                lead_vals.update({'active': True})
                lead.write(lead_vals)
                if origin == 'contact':
                    updated_contact_ids.append(lead.ids)
                elif origin == 'owner':
                    updated_owner_ids.append(lead.ids)
                elif origin == 'new_construction':
                    updated_construction_ids.append(lead.ids)
                elif data.get('ManagementCompanyParentId'):
                    updated_partner_ids.append(lead.ids)
                else:
                    updated_lead_ids.append(lead.ids)
            else:
                # Create new record
                lead = obj.create(lead_vals)
                # Prepare vals to create partner
                part_vals = {
                    'name': lead_vals.get('name', False),
                    'company_type': 'company',
                    'ref': referred,
                    'street': lead_vals.get('street', False),
                    'city': lead_vals.get('city', False),
                    'state_id': lead_vals.get('state_id', False),
                    'zip': lead_vals.get('zip', False),
                    'country_id': lead_vals.get('country_id', False),
                    'phone': lead_vals.get('phone', False),
                    'website': lead_vals.get('website', False),
                    'industry_id': lead_vals.get('industry_id', False),
                    'title': lead_vals.get('title', False),
                    'num_unit': data.get('NumberOfUnits', False)
                }

                if origin == 'contact':
                    contact_ids.append(lead.id)
                    # Update other partner info
                    part_vals.update({
                        'type': 'contact',
                        'partner_type': 'contact',
                        'company_type': 'person',
                    })
                    # Update vals for partner creation
                    if lead_vals.get('referred', False):
                        partner_id = partner_obj.search([('ref', '=', lead_vals.get('referred'))])
                        part_vals.update({'parent_id': partner_id and partner_id.id or False})
                    # Create new partner if new contact
                    contact_partner = partner_obj.create(part_vals)
                    new_contact_partner_list.append(contact_partner.id)
                elif origin == 'owner':
                    owner_ids.append(lead.id)
                    # Update other partner info
                    part_vals.update({
                        'partner_type': 'owner',
                    })
                    # Create new partner if new lead
                    owner_partner = partner_obj.create(part_vals)
                    new_owner_partner_list.append(owner_partner.id)
                elif origin == 'new_construction':
                    construction_ids.append(lead.id)
                    # Update parent
                    parent_id = False
                    if data.get('ApartmentId', False):
                        parent_id = partner_obj.search([('ref', '=', data.get('ApartmentId'))], limit=1)
                    # Update other partner info
                    part_vals.update({
                        'type': 'other',
                        'partner_type': 'new_construction',
                        'comment': data.get('Progress', False) or '',
                        'parent_id': parent_id and parent_id.id or False
                    })
                    # Create new partner if new construction
                    construction_partner = partner_obj.create(part_vals)
                    new_construction_partner_list.append(construction_partner.id)
                elif data.get('ManagementCompanyEntityId'):
                    partner_ids.append(lead.id)
                    # Update vals for management company creation
                    if lead_vals.get('partner_type', False) and \
                            lead_vals['partner_type'] == 'management_company':
                        # check if parent id for partner
                        parent = data.get('ManagementCompanyParentId', False)
                        entity = data.get('ManagementCompanyEntityId', False)
                        if parent:
                            parent_id = partner_obj.search([('ref', '=', parent)], limit=1)
                            if not parent_id:
                                # If no parent found create one
                                parent_vals = {'name': parent,
                                               'ref': parent}
                                parent_id = partner_obj.create(parent_vals)
                                # Create new Management company
                                part_vals.update({
                                    'parent_id': parent_id.id,
                                    'partner_type': 'management_company',
                                })
                                # Create new partner if new management company
                                manage_partner = partner_obj.create(part_vals)
                                new_manage_partner_list.append(manage_partner.id)
                            # Assign Parent value
                            lead.parent_id = parent_id.id
                        else:
                            # If already found partner don't create new partner
                            partner_id = partner_obj.search([('ref', '=', entity)], limit=1)
                            if not partner_id:
                                # Update other partner info
                                part_vals.update({
                                    'partner_type': 'management_company',
                                })
                                # Create new partner if new management company
                                manage_partner = partner_obj.create(part_vals)
                                new_manage_partner_list.append(manage_partner.id)
                            else:
                                # Update record if already found
                                partner_id.write(part_vals)
                else:
                    lead_ids.append(lead.id)
                # Update partner to created lead
                if lead_vals.get('referred', False):
                    partner_id = partner_obj.search([('ref', '=', lead_vals.get('referred'))])
                    if partner_id and not lead.partner_id:
                        lead.partner_id = partner_id.id
        row_version = rowversion_list and max(rowversion_list) or 0
        max_date = last_update_date and max(last_update_date) or 0

        if origin == 'contact':
            _logger.info(
                'ALN Data Connector. New Contacts Created : %s', new_contact_partner_list)
            _logger.info(
                'ALN Data Connector.Created Contacts : %s', contact_ids)
            _logger.info('ALN Data Connector.Updated Contacts : %s',
                         updated_contact_ids)
            _logger.info(
                'ALN Data Connector.Deleted Contacts : %s', removed_lead)
            if row_version:
                config_obj.sudo().set_param(
                    'alndata.contacts.rowversion', row_version)
        elif origin == 'owner':
            _logger.info('ALN Data Connector.Created Owners : %s', owner_ids)
            _logger.info('ALN Data Connector.Updated Owners : %s',
                         updated_owner_ids)
            _logger.info(
                'ALN Data Connector.Deleted Owners : %s', removed_lead)
            _logger.info(
                'ALN Data Connector.New Partners Created : %s',
                new_owner_partner_list)
        elif origin == 'new_construction':
            _logger.info('ALN Data Connector.New Created Constructions : %s',
                         new_construction_partner_list)
            _logger.info('ALN Data Connector.Created New Constructions : %s',
                         construction_ids)
            _logger.info('ALN Data Connector.Updated Constructions : %s',
                         updated_construction_ids)
            _logger.info('ALN Data Connector.Deleted Constructions : %s',
                         removed_lead)
            if max_date:
                config_obj.sudo().set_param(
                    'alndata.newconstructions.rowversion', max_date)
        else:
            if row_version:
                config_obj.sudo().set_param(
                    'alndata.managementcompanies.rowversion', row_version)
            _logger.info(
                'ALN Data Connector. New Management Companies Partners'
                ' : %s', new_manage_partner_list)
            _logger.info(
                'ALN Data Connector.Created Management Companies Partners'
                ' : %s', partner_ids)
            _logger.info(
                'ALN Data Connector.Updated Management Companies Partners '
                ': %s',
                updated_partner_ids)
            _logger.info(
                'ALN Data Connector.Deleted Management Companies Partners '
                ': %s',
                removed_partner)
            _logger.info(
                'ALN Data Connector.Created Management Companies Leads '
                ': %s', lead_ids)
            _logger.info('ALN Data Connector.Updated Management Companies '
                         'Leads : %s',
                         updated_lead_ids)
            _logger.info(
                'ALN Data Connector.Deleted Management Companies Leads :'
                ' %s', removed_lead)

    @api.model
    def sync_apartment_data(self):
        """Synchronize Apartments Data.
        This method is used to synchronize apartment data.
        """
        create_apart_ids = []
        update_apart_ids = []
        config_obj = self.env['ir.config_parameter']
        stage_obj = self.env['fsm.stage']
        industry_obj = self.env['res.partner.industry']
        partner_obj = self.env['res.partner']
        state_obj = self.env['res.country.state']
        fsm_obj = self.env['fsm.location']
        rowversion_list = []
        removed_apart_ids = []

        params = {'$expand': 'Addresses,PhoneNumbers'}
        apartment_key = config_obj.get_param(
            'alndata.apartments.rowversion')
        if apartment_key != '0':
            params.update({'$filter': 'RowVersion lt ' + apartment_key,
                           '$orderby': 'RowVersion'})
            old_apart = self.aln_auth_login('Apartments', params)
            apartments = [apart.get('ApartmentId') for apart in old_apart]
            removed_apart_ids = self.remove_data('fsm.location', apartments)
            params.update({'$filter': 'RowVersion gt ' + apartment_key,
                           '$orderby': 'RowVersion'})

        ind_ids = industry_obj.search([])
        for apart in self.aln_auth_login('Apartments', params):
            # contact = partner_obj
            industry = industry_obj
            prop = apart.get('Property')
            rowversion_list.append(int(apart.get('RowVersion')))
            stage = stage_obj.search(
                [('sequence', '=', prop.get('Status')),
                 ('stage_type', '=', 'location')],
                limit=1)
            # Get Industry
            prop_market = prop.get('Market', False)
            if prop_market:
                industry = industry_obj.search([('name', '=', prop_market)], limit=1)
                if not industry:
                    vals = {'name': prop_market}
                    industry = industry_obj.create(vals)
            # Get Owner
            owner_id = False
            if prop.get('OwnerId', False):
                owner_id = partner_obj.search([('ref', '=', prop.get('OwnerId'))], limit=1)

            image_data = b''
            if prop.get('AptPictureURL'):
                image_res = requests.get(prop.get('AptPictureURL'))
                image_data = image_res.content
            # Geolocation
            geo = apart.get('GeoLocation', False)
            # Prepare apartment vals
            apartment_vals = {
                'ref': apart.get('ApartmentId'),
                'stage_id': stage.id,
                'name': prop.get('AptName'),
                'email': prop.get('EMailAddress'),
                'industry_id': industry and industry.id or False,
                'aln_id': prop.get('ALNId', False),
                'owner_id': owner_id and owner_id.id or False,
                'type': 'other',
                'partner_type': 'apartment',
                'company_type': 'company',
                'num_of_unit': prop.get('NumUnits'),
                'year_built': prop.get('YearBuilt'),
                'year_remodeled': prop.get('YearRemodeled'),
                'direction': prop.get('Directions'),
                'notes': prop.get('PropertyDescription'),
                'website': prop.get('AptHomePage'),
                'image': base64.b64encode(image_data),
                'tz': us_timezone.get(prop.get('TimeZone', '').strip(), ''),
                'partner_latitude': geo.get('GPSLatitude', False),
                'partner_longitude': geo.get('GPSLongitude', False)
            }
            if prop.get('CurrManager'):
                contact = partner_obj.search(
                    [('name', '=', prop.get('CurrManager')),
                     ('partner_type', '=', 'contact')],
                    limit=1)
                apartment_vals.update({'contact_id': contact and contact.id})
            # Get Parent Id from Regional Management
            if prop.get('RegionalManagementCompanyId', False):
                management_company = partner_obj.search(
                    [('ref', '=', prop.get('RegionalManagementCompanyId')),
                     ('partner_type', '=', 'management_company')],
                    limit=1)
                apartment_vals.update(
                    {
                        'parent_id': management_company and
                                     management_company.id
                    }
                )
            # Get Parent Id from Corporate Management
            if not management_company and prop.get('CorporateManagementCompanyId', False):
                management_company = partner_obj.search(
                    [('ref', '=', prop.get('CorporateManagementCompanyId')),
                     ('partner_type', '=', 'management_company')],
                    limit=1)
                apartment_vals.update(
                    {
                        'parent_id': management_company and
                                     management_company.id}
                )
            # Find partner else pass undefined customer
            partner_id = False
            if apartment_vals.get('ref', False):
                partner_id = partner_obj.search([('ref', '=', apartment_vals.get('ref'))], limit=1)
            if not partner_id:
                partner_id = self.env.ref(
                    'connector_alndata.undefined_customer')
            apartment_vals.update({'contact_id': partner_id.id})
            if prop.get('OwnerId', False):
                owner = partner_obj.search(
                    [('ref', '=', prop.get('OwnerId')),
                     ('partner_type', '=', 'owner')],
                    limit=1)
                apartment_vals.update(
                    {
                        'owner_id': owner and owner.id,
                        'partner_id': (owner and owner.id) or partner_id.id})
            if apart.get('Addresses', False):
                address = apart['Addresses'][0]
                state = self.get_state(state_obj,
                                       address.get('AddressState'))
                country_id = state and state.country_id.id or 0
                apartment_vals.update(
                    {
                        'street': address.get('AddressLine1'),
                        'street2': address.get('AddressLine2'),
                        'city': address.get('AddressCity'),
                        'state_id': state.id,
                        'zip': address.get('AddressZIP'),
                        'country_id': country_id,
                    })
            if apart.get('PhoneNumbers', False):
                numbers = apart['PhoneNumbers']
                for num in numbers:
                    if num.get('IsPrimary') == 'Y':
                        apartment_vals.update({
                            'phone': num.get('Number')
                        })
                    if (num.get('PhoneNumberType') == "Fax Number" and
                            num.get('ManagementCompanyParentId')):
                        apartment_vals.update({
                            'fax': num.get('Number')
                        })
            fsm_location = fsm_obj.search(
                [('name', '=', prop.get('AptName')),
                 ('ref', '=', apart.get('ApartmentId')),
                 # Checked the fetched record exists in the system or not.
                 # sometime record is exist but it's archived.
                 # so it will not get in the search method.
                 # so it will go to create a new record but there is a
                 # SQL unique constraint on the 'ref' field.
                 # so it will raise the constraint error.
                 # To fix this issue added this domain.
                 '|',
                 ('active', '=', True),
                 ('active', '=', False)],
                limit=1)

            if not fsm_location:
                # If Inventory location not found
                # update from customer's Customer Location
                if not apartment_vals.get('inventory_location_id', False):
                    location = partner_id.property_stock_customer and \
                               partner_id.property_stock_customer.id or False
                if not location:
                    _logger.info(
                        'ALN Data Connector: Customer : %s location not found, please configure',
                        partner_id)
                else:
                    apartment_vals.update({'inventory_location_id': location})
                # Pass values in ctx and then update on partner create
                partner_ctx = {'ref': apartment_vals.get('ref'),
                               'partner_type': 'apartment',
                               'OwnerId': apartment_vals.get('owner_id'),
                               'industry_id': industry and industry.id or False,
                               'RegionalManagementCompanyId': prop.get('RegionalManagementCompanyId', False),
                               'CorporateManagementCompanyId': prop.get('CorporateManagementCompanyId', False)
                               }
                # Create Apartments
                fsm = fsm_obj.with_context(partner_ctx).create(apartment_vals)
                create_apart_ids.append(fsm.id)
            else:
                if not fsm_location.active:
                    apartment_vals.update({'active': True})
                # Update Apartments
                fsm_location.write(apartment_vals)
                update_apart_ids.append(fsm_location.id)
        row_version = rowversion_list and max(rowversion_list) or 0
        if row_version:
            config_obj.sudo().set_param(
                'alndata.apartments.rowversion', row_version)
        _logger.info(
            'ALN Data Connector.Created Fsm Location : %s', create_apart_ids)
        _logger.info(
            'ALN Data Connector.Updated Fsm Location : %s', update_apart_ids)
        _logger.info(
            'ALN Data Connector.Deleted Fsm Location : %s', removed_apart_ids)

    @api.model
    def sync_aln_data_with_threading(self):
        """Synchronize data with ALN Data By Threading.
        This method is used to get data from ALN Data usinf threading.
        """
        _logger.info('ALN Data Connector. Starting the synchronization...')
        new_cr = sql_db.db_connect(self.env.cr.dbname).cursor()
        uid, context = self.env.uid, self.env.context
        with api.Environment.manage():
            self.env = api.Environment(new_cr, uid, context)
            # Get Market Data
            self.sync_market_data()

            # Get Sub-Market Data
            self.sync_submarket_data()

            # Get Owner Data
            self.sync_owner_contact_data(origin='owner')

            # Get Contact Data
            self.sync_owner_contact_data('contact')

            # Get Management Companies Data
            self.sync_owner_contact_data()

            # Get the New Constructions Data
            self.sync_owner_contact_data('new_construction')

            # Get the Apartment Data
            self.sync_apartment_data()

            new_cr.commit()
            new_cr.close()
        _logger.info('ALN Data Connector. Synchronization successful.')

    @api.model
    def _cron_sync_with_aln(self):
        """Synchronize data with ALN Data.
        This method is used to get data from ALN Data and create data in odoo.
        """
        api_key = self.env['ir.config_parameter'].get_param('alndata.api.key')
        if api_key == '0':
            action = self.env.ref('base.ir_config_list_action')
            msg = _('Cannot find a ALN Data URL and API key, '
                    'You should configure it. '
                    '\nPlease go to System Parameters.')
            raise RedirectWarning(msg, action.id,
                                  _('Go to the configuration panel'))
        thred_cal = threading.Thread(
            target=self.sync_aln_data_with_threading)
        thred_cal.start()
