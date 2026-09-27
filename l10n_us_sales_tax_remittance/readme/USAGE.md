1. In **Settings > US Tax**, set the Sales Tax Payable account, the Collection
   Allowance income account, and the Remittance (purchase) journal.
2. In **US Tax > Configuration > Tax Authorities**, add one record per state
   you file in: the state, its Department of Revenue vendor, your registration
   number, and that state's collection-allowance rate/cap. A state without a
   record falls back to the company default authority and the built-in rate.
3. Open a generated (or filed) **US Tax Return** and click **Create
   Remittance**. This books a vendor bill against the state's DOR that clears
   the sales-tax-payable accrual, credits the allowance to income, and owes the
   net. When the return ties out to the ledger, the payable is reconciled
   automatically.
4. Read the **GL Tie-Out**: ``Tax Collected (GL)`` is the period's
   ledger-collected tax for that state, and a non-zero ``Tie-Out Variance``
   means the return does not match the ledger - investigate before filing. With
   a variance the bill is posted but the payable is **not** auto-reconciled.
5. When you pay the DOR from the bank, the shipped *Sales Tax Remittance*
   reconcile model matches the payment to the remittance bill by partner.

Collected tax accrues to one shared payable account; each posting is tagged
with its state, so each state's remittance only touches its own liabilities -
no per-state sub-accounts are needed.
