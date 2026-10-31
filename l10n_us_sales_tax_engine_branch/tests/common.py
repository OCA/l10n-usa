# Copyright 2026 Binhex - Edilio Escalona Almira.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo.fields import Command
from odoo.tests import new_test_user

from odoo.addons.l10n_us_sales_tax_engine.tests.common import UsTaxBaseTest


class UsTaxBranchCommon(UsTaxBaseTest):
    """Company tree, rates and customers shared by the branch tests.

    The root is the test company, located in Miami (FL 33101, 7%). Branch A1
    sits in the same state with its own ZIP (6.5%) and branch A2 in another
    ZIP of the same state (7.25%), so the applied rate tells which address
    the engine used.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.env["ir.config_parameter"].sudo().set_param(
            "l10n_us_tax.engine_mode", "local"
        )
        cls.tx = cls.env["res.country.state"].search(
            [("code", "=", "TX"), ("country_id", "=", cls.us.id)], limit=1
        )
        cls._create_zip_rate(
            zip_code="32991",
            state=cls.fl,
            county="BRANCH A1",
            state_rate=0.06,
            county_rate=0.005,
        )
        cls._create_zip_rate(
            zip_code="32992",
            state=cls.fl,
            county="BRANCH A2",
            state_rate=0.06,
            county_rate=0.0125,
        )
        cls._create_zip_rate(
            zip_code="75999",
            state=cls.tx,
            county="BRANCH TX",
            state_rate=0.0625,
            county_rate=0.02,
        )

        cls.root = cls.env.company
        cls.root.write(
            {
                "street": "1 Root Street",
                "city": "Miami",
                "zip": "33101",
                "state_id": cls.fl.id,
                "country_id": cls.us.id,
            }
        )
        cls.branch_a1 = cls._create_branch("US Tax Branch A1", "32991", cls.fl)
        cls.branch_a2 = cls._create_branch("US Tax Branch A2", "32992", cls.fl)

        cls.partner_tx = cls.env["res.partner"].create(
            {
                "name": "Branch Customer TX",
                "street": "1 Texas Road",
                "city": "Dallas",
                "zip": "75999",
                "state_id": cls.tx.id,
                "country_id": cls.us.id,
            }
        )
        cls.partner_foreign = cls.env["res.partner"].create(
            {
                "name": "Branch Customer ES",
                "city": "Madrid",
                "zip": "28001",
                "country_id": cls.env.ref("base.es").id,
            }
        )
        cls.partner_no_address = cls.env["res.partner"].create(
            {"name": "Branch Walk-in Customer"}
        )
        cls.user = new_test_user(
            cls.env,
            login="us_tax_branch_user",
            groups="sales_team.group_sale_salesman,account.group_account_invoice",
            company_id=cls.root.id,
            company_ids=[Command.set((cls.root | cls.branch_a1 | cls.branch_a2).ids)],
        )

    @classmethod
    def _create_zip_rate(cls, zip_code, state, county, state_rate, county_rate):
        jurisdiction = cls.env["us.tax.jurisdiction"].create(
            {
                "name": county.title(),
                "type": "county",
                "state_id": state.id,
                "county": county,
            }
        )
        cls.env["us.tax.rate"].create(
            {
                "jurisdiction_id": jurisdiction.id,
                "product_tax_category_id": cls.cat_tangible.id,
                "state_rate": state_rate,
                "county_rate": county_rate,
                "effective_date": "2020-01-01",
                "source": "test",
            }
        )
        cls.env["us.tax.zip.mapping"].create(
            {
                "zip": zip_code,
                "state_id": state.id,
                "jurisdiction_id": jurisdiction.id,
                "county": county,
                "confidence": 1.0,
                "source": "test",
            }
        )

    @classmethod
    def _create_branch(cls, name, zip_code, state):
        return cls.env["res.company"].create(
            {
                "name": name,
                "parent_id": cls.root.id,
                "street": f"1 {name} Street",
                "city": "Branch City",
                "zip": zip_code,
                "state_id": state.id,
                "country_id": cls.us.id,
            }
        )

    def _create_order(self, company, partner):
        return (
            self.env["sale.order"]
            .with_user(self.user)
            .with_company(company)
            .create(
                {
                    "company_id": company.id,
                    "partner_id": partner.id,
                    "order_line": [
                        Command.create(
                            {
                                "product_id": self.product.id,
                                "product_uom_qty": 1.0,
                                "price_unit": 100.0,
                            }
                        )
                    ],
                }
            )
        )
