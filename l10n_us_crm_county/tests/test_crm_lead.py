from odoo.tests import TransactionCase


class TestCrmLead(TransactionCase):
    def test_compute_partner_address_values(self):
        lead = self.env.ref("crm.crm_case_1")
        self.assertFalse(lead.county_id)
        partner = self.env.ref("base.res_partner_1")
        partner.county_id = self.env.ref(
            "l10n_us_base_county.res_country_state_county_1057"
        ).id
        lead.partner_id = partner
        self.assertEqual(
            lead.county_id,
            partner.county_id,
            "should have updated lead with partner county",
        )

    def test_create_customer(self):
        lead = self.env.ref("crm.crm_case_1")
        lead.county_id = self.env.ref(
            "l10n_us_base_county.res_country_state_county_1057"
        ).id
        customer = lead._create_customer()
        self.assertEqual(
            customer.county_id,
            lead.county_id,
            "should have created partner with lead county",
        )
