# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import hashlib
import logging

from odoo import api, fields, models

from ..services.address_resolver import is_us_address
from ..services.provider_base import ProviderError

_logger = logging.getLogger(__name__)


class UsTaxAutoMixin(models.AbstractModel):
    """Automatic US tax recalculation shared by sale.order and account.move.

    A document supplies _us_tax_get_address(), _us_tax_get_date(),
    _us_tax_get_lines(), _us_tax_engine_run(), _us_tax_state_domain() and
    _us_tax_state_depends(). The engine reads the first three too, so an
    override moves the fingerprint and what gets taxed at once.

    An order is priced by the write that confirms it, at its confirmation
    date; a move by _post(), before the core writes state = 'posted'.
    us_tax_skip_auto keeps the engine's own writes from starting another
    calculation. The fingerprint does not move under the engine's output
    because price_subtotal does not change with a tax-excluded tax, which is
    why the engine pins price_include_override on the taxes it creates.
    """

    _name = "us.tax.auto.mixin"
    _description = "US Tax Automatic Recalculation"

    us_tax_source = fields.Char(
        string="Tax Source",
        help="Source used for the last US tax calculation.",
    )
    us_tax_calculated_at = fields.Datetime(
        string="Tax Calculated At",
    )
    us_tax_auto_attempt_at = fields.Datetime(
        string="US Tax Last Attempt",
        readonly=True,
        copy=False,
        help=(
            "When the automation last tried to recalculate this document, "
            "whether or not the calculation succeeded."
        ),
    )
    us_tax_input_hash = fields.Char(
        string="US Tax Input Hash",
        compute="_compute_us_tax_input_hash",
        store=True,
        copy=False,
        help="Fingerprint of the inputs the tax engine reads for this document.",
    )
    us_tax_calculated_hash = fields.Char(
        string="US Tax Calculated Hash",
        readonly=True,
        copy=False,
        help="Value of the input hash at the time of the last calculation.",
    )
    us_tax_is_stale = fields.Boolean(
        string="US Tax Outdated",
        compute="_compute_us_tax_is_stale",
        store=True,
        copy=False,
        help=(
            "The tax inputs changed after the last US tax calculation and the "
            "document can still be recalculated."
        ),
    )
    us_tax_engine_available = fields.Boolean(
        string="US Tax Engine Available",
        compute="_compute_us_tax_engine_available",
        help="Technical field: exposes l10n_us_tax.engine_active to the views.",
    )

    def _compute_us_tax_engine_available(self):
        """Expose l10n_us_tax.engine_active to the views.

        Not stored and without depends: the ORM cannot follow a config
        parameter, so the value is read again on every form read.
        """
        ICP = self.env["ir.config_parameter"].sudo()
        available = ICP.get_param("l10n_us_tax.engine_active", "False") == "True"
        for record in self:
            record.us_tax_engine_available = available

    def _us_tax_auto_mode(self):
        """Return the automation mode in force: off or on_validate.

        A disabled engine means off whatever mode is stored. A database that
        never chose a mode calculates on validation, as 18.0.1.2.x did.
        """
        ICP = self.env["ir.config_parameter"].sudo()
        if ICP.get_param("l10n_us_tax.engine_active", "False") != "True":
            return "off"
        return ICP.get_param("l10n_us_tax.auto_mode") or "on_validate"

    def _us_tax_partner_address_fields(self):
        """Return the res.partner fields the address is built from.

        Read when the registry builds the field triggers, so an override takes
        effect on module upgrade. The same holds for the next three hooks.
        """
        return ["zip", "state_id", "city", "street", "country_id"]

    def _us_tax_partner_fields(self):
        """Return the partner links the address may be resolved through."""
        return ["partner_id", "partner_shipping_id"]

    def _us_tax_extra_depends(self):
        """Return the model-specific dependencies of the input hash."""
        return []

    def _us_tax_state_depends(self):
        """Return the stored fields _us_tax_state_domain() is expressed on."""
        return []

    def _us_tax_hash_depends(self):
        """Expand the hooks above into the @api.depends of the hash.

        A dotted path already makes each of its prefixes a trigger, so the bare
        partner links are not listed.
        """
        depends = [
            f"{partner_field}.{address_field}"
            for partner_field in self._us_tax_partner_fields()
            for address_field in self._us_tax_partner_address_fields()
        ]
        depends.append("partner_id.us_tax_exempt")
        return depends + self._us_tax_extra_depends() + self._us_tax_state_depends()

    @api.depends(lambda self: self._us_tax_hash_depends())
    def _compute_us_tax_input_hash(self):
        """Fingerprint the engine inputs, without calculating any tax.

        A document without a usable US address gets no hash and is never
        outdated. Only documents inside _us_tax_state_domain() are assigned, so
        a partner address change does not rewrite posted, cancelled, locked or
        invoiced documents.

        To widen the fingerprint, override this method with its own
        @api.depends and a call to super(), which adds the triggers, and
        _us_tax_build_input_hash(), which adds the value.
        """
        allowed = self._us_tax_auto_allowed()
        for document in self:
            if document in allowed:
                document.us_tax_input_hash = document._us_tax_build_input_hash()

    @api.depends(
        lambda self: [
            "us_tax_input_hash",
            "us_tax_calculated_hash",
            "us_tax_auto_attempt_at",
        ]
        + self._us_tax_state_depends()
    )
    def _compute_us_tax_is_stale(self):
        """Flag the documents that are outdated and still recalculable.

        Stored so they can be searched. A document is outdated only once a
        calculation was attempted: a failed first calculation leaves no
        calculated hash, and us_tax_auto_attempt_at is what keeps it outdated.

        The single callable holds the whole list because api.depends() drops
        the plain strings once its first argument is callable.
        """
        allowed = self._us_tax_auto_allowed()
        for document in self:
            document.us_tax_is_stale = (
                document in allowed
                and bool(
                    document.us_tax_calculated_hash or document.us_tax_auto_attempt_at
                )
                and document.us_tax_input_hash != document.us_tax_calculated_hash
            )

    def _us_tax_get_address(self):
        """Return the address dict the engine would resolve for self."""
        raise NotImplementedError

    def _us_tax_get_date(self):
        """Return the document date as an ISO string, empty when unset."""
        raise NotImplementedError

    def _us_tax_get_lines(self):
        """Return the lines the engine would price."""
        raise NotImplementedError

    def _us_tax_build_input_hash(self):
        """Return the SHA-256 of the engine inputs, or False when unusable."""
        self.ensure_one()
        address = self._us_tax_get_address()
        if not address or not is_us_address(address):
            return False
        if not address.get("zip") or not address.get("state"):
            return False
        partner = self.partner_id.sudo()
        parts = [
            address.get("zip", ""),
            address.get("state", ""),
            address.get("city", ""),
            address.get("country_code", ""),
            "1" if partner.us_tax_exempt else "0",
            self._us_tax_get_date(),
            str(self.company_id.id or ""),
        ]
        parts.extend(self._us_tax_get_lines()._us_tax_hash_parts())
        return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()

    def _us_tax_state_domain(self):
        """Domain of the documents the automation may touch, set per model.

        A domain rather than a filtered() lambda, so it also serves a search.
        """
        return []

    def _us_tax_auto_allowed(self):
        """Return the subset of self the automation is allowed to touch."""
        return self.filtered_domain(self._us_tax_state_domain())

    def _us_tax_recalculate(self):
        """Recalculate one document that is being confirmed or posted.

        The attempt is stamped first, so a failed first calculation leaves the
        document outdated. _calculate_on_validation() applies the fail policy.
        """
        self.ensure_one()
        self.with_context(us_tax_skip_auto=True).write(
            {"us_tax_auto_attempt_at": fields.Datetime.now()}
        )
        self.env["us.tax.engine.service"]._calculate_on_validation(
            self, lambda document: document._us_tax_calculate()
        )

    def _us_tax_auto_recalculate(self, force=False):
        """Recalculate the documents in self while they are validated.

        Only while an order is confirmed or a move posted, which is when
        us_tax_validating is set, and never in the off mode. Rates, rules and
        nexus are not in the fingerprint, so the confirmation write and
        _post() pass force and always price the document. Any other write made
        during the validation, such as sale_stock's on procurement_group_id,
        recalculates only when the fingerprint moved.
        """
        if self.env.context.get("us_tax_skip_auto"):
            return
        if self._us_tax_auto_mode() == "off":
            return
        if not self.env.context.get("us_tax_validating"):
            return
        for record in self._us_tax_auto_allowed():
            if force or record.us_tax_input_hash != record.us_tax_calculated_hash:
                record._us_tax_recalculate()

    def _us_tax_engine_run(self):
        """Run the engine for self and return its result dict."""
        raise NotImplementedError

    def action_calculate_us_tax(self):
        """Recalculate US tax from the Calculate US Tax button.

        Under the block policy a provider outage reaches the user as a UserError
        instead of a traceback. _calculate_on_validation() calls
        _us_tax_calculate() because it needs the ProviderError itself.
        """
        try:
            return self._us_tax_calculate()
        except ProviderError as exc:
            raise self.env["us.tax.engine.service"]._provider_failure_error(
                self, exc
            ) from exc

    def _us_tax_calculate(self):
        """Recalculate US tax for this document.

        Does nothing outside _us_tax_state_domain(), where the engine cannot
        write the tax. Runs under us_tax_skip_auto so the engine's own writes
        do not start a second calculation.

        The calculated hash is stamped only when the tax landed on the lines.
        A failure clears it and stamps the attempt, so the document reads as
        outdated. A skip (non-US, no ZIP) clears both: the engine's tax was
        just taken off and the document is no longer priced.
        """
        self.ensure_one()
        if self not in self._us_tax_auto_allowed():
            return
        document = self.with_context(us_tax_skip_auto=True)
        try:
            result = document._us_tax_engine_run()
            source = self.env["us.tax.engine.service"]._result_source(result)
            now = fields.Datetime.now()
            values = {"us_tax_source": source, "us_tax_calculated_at": now}
            if source in ("skip_non_us", "skip_no_address"):
                values["us_tax_calculated_hash"] = False
                values["us_tax_auto_attempt_at"] = False
            elif source == "error":
                values["us_tax_calculated_hash"] = False
                values["us_tax_auto_attempt_at"] = now
            elif source != "disabled":
                values["us_tax_calculated_hash"] = document.us_tax_input_hash
            document.write(values)
            return result
        except Exception as exc:
            _logger.error(
                "US Tax calculation error on %s %s: %s", self._name, self.name, exc
            )
            raise

    def write(self, vals):
        """Recalculate the tax on validation.

        The write that changes the state is the one confirming an order, so it
        forces the calculation.
        """
        res = super().write(vals)
        self._us_tax_auto_recalculate(force="state" in vals)
        return res
