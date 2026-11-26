Closes the loop from a generated sales-tax return to the remittance, the
general ledger, and the vendor bill.

**Create Remittance** on a return books a vendor bill against the configured
tax authority (DOR) that:

- debits the **sales-tax-payable** accrual account by the total tax collected,
  clearing the period's liability;
- credits the **vendor collection allowance / timely-filing discount** to
  income (the portion of the tax the seller keeps);
- owes the **net** to the authority;
- and **reconciles** the payable debit against the period's collected-tax
  credits.

It also shows a **GL tie-out**: the tax collected on the payable account per
the ledger vs. the return total, flagging any variance so a return that does
not reconcile is visible before filing.

Configure the payable / allowance accounts and remittance journal in
Settings > US Tax.

**Per-state tax authorities.** A seller registered in several states remits to
a different Department of Revenue for each. Configure one authority per state
(Settings > US Tax > Tax Authorities) with its vendor, registration number,
and that state's collection-allowance rate/cap; each return resolves its
authority by state and bills the right DOR, falling back to the company
default when no per-state authority exists.

**One shared payable account, reconciled per state.** Collected tax accrues to
a single sales-tax-payable account - no per-state sub-accounts cluttering the
chart. Each tax posting is tagged with its state, so a state's remittance
reconciles only that state's liabilities. A reconcile-model template (match
the DOR bank payment to its remittance bill by partner) ships as demo data.
