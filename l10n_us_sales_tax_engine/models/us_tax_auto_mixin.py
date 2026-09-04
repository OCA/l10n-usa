# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import hashlib
import logging

import psycopg2

from odoo import api, fields, models

from ..services.address_resolver import is_us_address

_logger = logging.getLogger(__name__)


class UsTaxAutoMixin(models.AbstractModel):
    """Automatic US tax recalculation shared by sale.order and account.move.

    The mixin owns every us_tax_* field, every compute, the input hash
    template and the single CRUD entry point. A concrete document supplies
    only _us_tax_get_address(), _us_tax_get_date(), _us_tax_get_lines(),
    _us_tax_engine_run(), _us_tax_state_domain() and _us_tax_state_depends().
    The first three are also what us.tax.engine.service reads, so a
    downstream override moves the fingerprint and what gets taxed at once.

    Every create() and write() on the document and line models funnels into
    _us_tax_auto_recalculate(), which gates on the us_tax_skip_auto context
    key, then on _us_tax_auto_enabled(), then on _us_tax_state_domain() and
    finally on the comparison of us_tax_input_hash against
    us_tax_calculated_hash. Two of those gates are what makes the automation
    terminate.

    us_tax_skip_auto closes the engine's own writes. action_calculate_us_tax
    binds the key before calling the service and with_context rebinds the
    environment, so the lines read inside _apply_to_sale_order and
    _apply_to_invoice carry it, and writing their tax re-enters the line
    write() override on a recordset that returns at the context check.
    sudo() flips env.su and keeps the key.

    The hash comparison closes everything that carries no key, and it holds
    for a narrower reason than it appears to. The engine's output is one hop
    away from the fingerprint: order_line.price_subtotal and
    invoice_line_ids.price_subtotal are in the @api.depends, and the core
    computes them from tax_id / tax_ids. What keeps the fingerprint fixed is
    that price_subtotal is invariant under a tax-excluded tax, which is why
    the engine pins price_include_override on every account.tax it creates
    instead of letting it fall back to res.company.account_price_include.

    Confirming a sale order needs no override on top of that entry point:
    the core's own action_confirm() writes _prepare_confirmation_values()
    unconditionally, before action_lock(), so the write reaches write() with
    the order still inside _us_tax_state_domain(). Letting that write be the
    trigger is also what prices the order at its confirmation date, since
    the core stamps date_order in the same values. Posting a move does need
    account.move._post() to call the entry point explicitly, because the
    core writes state = 'posted' inside super() and the move leaves the
    state domain within that call.
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
        """Expose the engine switch to the views.

        Deliberately not stored and without @api.depends: a
        config_parameter is not a dependency the ORM can follow, so the
        value is read again on every form read. It exists only so the
        views can hide the "Calculate US Tax" button, which has no other
        way of reading that parameter.
        """
        ICP = self.env["ir.config_parameter"].sudo()
        available = ICP.get_param("l10n_us_tax.engine_active", "False") == "True"
        for record in self:
            record.us_tax_engine_available = available

    def _us_tax_auto_enabled(self):
        """Return True when the engine AND its automation are both enabled.

        The engine flag is checked on top of the automation flag because
        res.config.settings is not the only writer of ir.config_parameter:
        set_param() bypasses the settings form, so the stored pair can be
        inconsistent and only a runtime check catches it.
        """
        ICP = self.env["ir.config_parameter"].sudo()
        return (
            ICP.get_param("l10n_us_tax.engine_active", "False") == "True"
            and ICP.get_param("l10n_us_tax.auto_calculate", "False") == "True"
        )

    def _us_tax_partner_address_fields(self):
        """Return the res.partner fields the resolved address is built from.

        Evaluated once per registry build, when the @api.depends callable
        runs (odoo/modules/registry.py builds the field triggers then), so
        this has to return a static list and a downstream override only
        takes effect on module upgrade.
        """
        return ["zip", "state_id", "city", "street", "country_id"]

    def _us_tax_partner_fields(self):
        """Return the partner links the address may be resolved through.

        Same evaluation constraint as _us_tax_partner_address_fields.
        """
        return ["partner_id", "partner_shipping_id"]

    def _us_tax_extra_depends(self):
        """Return the model-specific dependencies of the input hash.

        Same evaluation constraint as _us_tax_partner_address_fields.
        """
        return []

    def _us_tax_state_depends(self):
        """Return the stored fields _us_tax_state_domain() is expressed on.

        The hash and the staleness flag are both kept inside that domain,
        so the fields deciding membership are dependencies of both. They
        are stored fields of the document itself, so they add no inverse
        traversal to the trigger tree.

        Same evaluation constraint as _us_tax_partner_address_fields.
        """
        return []

    def _us_tax_hash_depends(self):
        """Expand the hooks above into the @api.depends of the hash.

        The bare partner links are deliberately absent: resolve_depends()
        yields every prefix of a dotted path, so "partner_id.zip" already
        registers partner_id itself as a trigger.
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

        The address is resolved through the very same helpers the engine
        uses, so a value the engine normalizes away (a ZIP+4, a lowercase
        city) never shows up as a change. Documents without a usable US
        address get no hash at all: the engine skips them, so they can
        never be outdated.

        A downstream module widens the fingerprint by overriding this
        method with its own @api.depends and calling super():
        Field.get_depends() collects _depends from every override of the
        compute in the MRO. Redefining the field with the depends= kwarg
        instead replaces the list rather than extending it.

        The fingerprint is only maintained inside _us_tax_state_domain().
        Leaving the rest unassigned is what keeps a partner address change
        from rewriting posted, cancelled, locked and invoiced documents:
        the inverse traversal still marks them to recompute, but no UPDATE
        follows, so no write_uid/write_date is stamped behind the core's
        own guards. A stored compute may legally leave records unassigned,
        because compute_value drops the whole batch from the to-compute set
        before running the method.

        Writing a customer address therefore costs a fixed number of
        queries, whatever the number of documents that customer has: the
        ORM prefetches them in one read and lands their two fingerprint
        columns in a single UPDATE. What scales is the SHA-256 of each,
        in Python. The engine stays out of it — marking a document
        outdated never leaves the database, so the transaction that
        writes the address spends no provider quota and waits on no HTTP
        call. Recalculating is left to the document's own next write, to
        the banner's button or to the cron.
        _compute_us_tax_is_stale() reads the same domain for the same
        reason, so the two columns move together or not at all.

        _us_tax_state_depends() is in the depends for exactly this reason:
        a document leaving the domain and coming back keeps a fingerprint
        frozen at the moment it left, and only the state change itself can
        mark it for recompute.
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

        Stored, because comparing two columns is not expressible as an
        Odoo domain and the cron has to reach these documents through
        SQL. Carrying _us_tax_state_domain() inside makes the field the
        single definition behind the cron, the banner and the manual
        button: a locked, invoiced, posted or cancelled document reads
        as up to date, because nothing can be applied to it.

        A document nobody ever tried to calculate is not outdated, and
        that is what the attempt marks. Resting on the calculated hash
        alone would read a first calculation that failed as "never
        calculated" — the hash is deliberately left alone on failure —
        and drop the document out of the cron's queue for good, with no
        banner to show for it either. us_tax_auto_attempt_at is stamped
        by _us_tax_recalculate() outside its savepoint precisely so it
        survives that failure.

        That is also why the write guard in _us_tax_auto_recalculate()
        compares the two hashes by hand instead of reading this field: a
        document being created has no attempt yet and is precisely the
        one to calculate.

        A single callable holds the whole dependency list because
        api.depends() drops the plain strings as soon as its first
        argument is callable.
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
        """Return the SHA-256 of the engine inputs, or False when unusable.

        The three hooks above are the only places the document types
        differ; everything the fingerprint covers is assembled here so a
        field enters both models' hash at once.
        """
        self.ensure_one()
        address = self._us_tax_get_address()
        if not address or not is_us_address(address):
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
        """Domain of the documents the automation is allowed to touch.

        Overridden per model. Expressed as a domain, not as a filtered()
        lambda, so the very same definition serves both the write/create
        guard and the cron's search.
        """
        return []

    def _us_tax_auto_allowed(self):
        """Return the subset of self the automation is allowed to touch."""
        return self.filtered_domain(self._us_tax_state_domain())

    def _us_tax_recalculate(self):
        """Recalculate one document, shielded from re-entrance and failures.

        us_tax_skip_auto stops the engine's own writes from coming back
        through the write()/create() overrides. A failure is logged and
        swallowed: an automatic recalculation must never block the write
        that triggered it. The document keeps its old calculated hash, so
        the cron picks it up again.

        That covers the ProviderError the block fail policy raises when
        every provider failed. The policy governs the manual Calculate US
        Tax button, where the user is waiting on the answer; letting it
        propagate here would make a provider outage enough to stop every
        draft document from being edited, confirmed or posted.

        The savepoint is what makes that promise true: whatever the
        failing calculation had already written is discarded, so the
        swallow cannot leave the document half updated. Being a flushing
        savepoint it clears the ORM cache and the pending recomputations
        too, and it flushes before opening, so whatever the caller had
        written in its own write() stays. The engine guards the write of
        the tax onto the lines with a savepoint of its own — that one
        reports through the "applied" key instead of raising, so it never
        reaches this handler.

        A database error is re-raised instead: swallowing it would leave
        the cursor aborted and take away the core's serialization retry,
        with the failure surfacing much later in a flush() that no longer
        names the engine.

        The attempt is stamped before the savepoint opens, so the
        rollback cannot take it with it. It is what keeps a document
        whose first calculation failed inside us_tax_is_stale, and hence
        inside the cron's queue, and it is what orders that queue.
        """
        self.ensure_one()
        self.with_context(us_tax_skip_auto=True).write(
            {"us_tax_auto_attempt_at": fields.Datetime.now()}
        )
        try:
            with self.env.cr.savepoint():
                self.with_context(us_tax_skip_auto=True).action_calculate_us_tax()
        except psycopg2.OperationalError:
            raise
        except Exception as exc:
            _logger.warning(
                "US Tax auto-calc failed on %s %s: %s", self._name, self.id, exc
            )

    def _us_tax_auto_recalculate(self):
        """Recalculate the documents in self whose inputs no longer match.

        The hash comparison is the only trigger guard: a field outside the
        hash's @api.depends leaves both hashes equal, so writing it never
        reaches the engine.
        """
        if self.env.context.get("us_tax_skip_auto"):
            return
        if not self._us_tax_auto_enabled():
            return
        for record in self._us_tax_auto_allowed():
            if record.us_tax_input_hash != record.us_tax_calculated_hash:
                record._us_tax_recalculate()

    def _us_tax_engine_run(self):
        """Run the engine for self and return its result dict."""
        raise NotImplementedError

    def action_calculate_us_tax(self):
        """Manual trigger — recalculate US tax for this document.

        Runs under us_tax_skip_auto: the engine writes the tax on every
        line, and that write re-enters the line write() override while
        us_tax_calculated_hash still holds the old value — without the
        flag the two hashes still differ there and a second, redundant
        calculation would fire before this one gets to stamp the hash.

        Returns without touching anything outside _us_tax_state_domain().
        The engine cannot apply a tax to a posted move or a locked order
        — tax_ids is frozen on the first, tax_id is a protected field on
        the second — and stamping the hash there would clear the warning
        for a calculation that never landed. The views hide both buttons
        under the same condition, so reaching this guard means a direct
        RPC call.

        The calculated hash is stamped only when the engine reports that
        the tax landed on the lines: _process() swallows the failure of
        its apply_fn and says so through the "applied" key, and every
        source that stands for "nothing was calculated" is excluded as
        well. Reaching this method with the engine switched off takes a
        direct RPC call, and stamping the hash there would clear the
        warning for a calculation that never ran. us_tax_source and
        us_tax_calculated_at are written either way, so the attempt stays
        visible on the document.
        """
        self.ensure_one()
        if self not in self._us_tax_auto_allowed():
            return
        document = self.with_context(us_tax_skip_auto=True)
        try:
            result = document._us_tax_engine_run()
            values = {
                "us_tax_source": result.get("source", ""),
                "us_tax_calculated_at": fields.Datetime.now(),
            }
            if result.get("applied", True) and result.get("source") not in (
                "disabled",
                "skip_non_us",
                "skip_no_address",
                "error",
            ):
                values["us_tax_calculated_hash"] = document.us_tax_input_hash
            document.write(values)
        except Exception as exc:
            _logger.error(
                "US Tax calculation error on %s %s: %s", self._name, self.name, exc
            )
            raise

    def write(self, vals):
        """Recalculate the tax when the write changed an engine input.

        The guard is the hash comparison alone, so writing a field
        outside the hash's @api.depends never reaches the engine.
        """
        res = super().write(vals)
        self._us_tax_auto_recalculate()
        return res

    @api.model
    def _us_tax_cron_recalculate_stale(self, limit=200):
        """Recalculate the documents left outdated by a change in their inputs.

        us_tax_is_stale is a stored column carrying the state domain, so
        the whole selection happens in SQL and limit is a real LIMIT. The
        state domain is repeated in the search to narrow the scan on the
        indexed state columns.

        Two searches rather than one ordered by a nullable column: the
        documents never attempted come first, then the least recently
        attempted. _us_tax_recalculate() stamps us_tax_auto_attempt_at on
        every document it takes, successful or not, and that is what keeps
        the queue moving — a recalculation that fails deliberately leaves
        us_tax_calculated_hash alone, so without the stamp the same
        lowest-id documents would be retried run after run and nothing
        behind them would ever be reached.

        Runs on the concrete document model: data/ir_cron.xml ships one
        record per model, so "model" in the cron code is a real recordset
        and a downstream addon adds a document type by shipping its own
        record instead of overriding a hook.
        """
        if not self._us_tax_auto_enabled():
            return
        domain = self._us_tax_state_domain() + [("us_tax_is_stale", "=", True)]
        records = self.search(
            domain + [("us_tax_auto_attempt_at", "=", False)], limit=limit
        )
        if len(records) < limit:
            records |= self.search(
                domain + [("us_tax_auto_attempt_at", "!=", False)],
                limit=limit - len(records),
                order="us_tax_auto_attempt_at",
            )
        if not records:
            return
        _logger.info(
            "US Tax cron: recalculating %s outdated %s",
            len(records),
            self._name,
        )
        for record in records:
            record._us_tax_recalculate()
