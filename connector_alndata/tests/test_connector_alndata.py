# Copyright (C) 2019 Open Source Integrators
# Copyright (C) 2019 Serpent Consulting Services Pvt. Ltd.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo.tests.common import TransactionCase

import logging
_logger = logging.getLogger(__name__)


class TestConnectorAlndata(TransactionCase):

    def setUp(self):
        super(TestConnectorAlndata, self).setUp()
        self.config_model = self.env['ir.config_parameter']
        self.crm_obj = self.env['crm.lead']

    def test_cron_sync_with_aln(self):
        """
            Test cron job for synchronization data.
        """
        self.config_model.set_param(
            'alndata.api.key',
            'b85f4d81-d726-42d4-a524-30f75e28a1ac')
        self.crm_obj._cron_sync_with_aln()
