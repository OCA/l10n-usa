# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import models


class UsTaxProvider(models.Model):
    _inherit = "us.tax.provider"

    def _provider_service_classes(self):
        # The engine's documented extension point: register a provider by
        # extending the {code: class} registry — no edit to the engine.
        from ..services import provider_api_ninjas  # noqa: PLC0415

        classes = super()._provider_service_classes()
        classes["api_ninjas"] = provider_api_ninjas.ProviderApiNinjas
        return classes
