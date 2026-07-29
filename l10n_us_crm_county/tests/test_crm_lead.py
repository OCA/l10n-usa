from odoo.tests import TransactionCase


class TestCrmLead(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.state_us = cls.env.ref("base.state_us_5")

        cls.county = cls.env["res.country.state.county"].create(
            {
                "name": "Test County",
                "state_id": cls.state_us.id,
            }
        )

        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Test Partner",
                "country_id": cls.env.ref("base.us").id,
                "state_id": cls.state_us.id,
            }
        )

    def test_compute_partner_address_values(self):
        lead = self.env["crm.lead"].create(
            {
                "name": "Test Lead",
            }
        )
        self.assertFalse(lead.county_id)
        self.partner.county_id = self.county.id
        lead.partner_id = self.partner
        self.assertEqual(
            lead.county_id,
            self.partner.county_id,
            "should have updated lead with partner county",
        )

    def test_create_customer(self):
        lead = self.env["crm.lead"].create(
            {
                "name": "Test Lead",
                "county_id": self.county.id,
            }
        )
        customer = lead._create_customer()
        self.assertEqual(
            customer.county_id,
            lead.county_id,
            "should have created partner with lead county",
        )
