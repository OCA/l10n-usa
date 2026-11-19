- When a document has no shipping address of its own and the engine
  falls back to the customer's `delivery` child contact, a change to
  *that contact's* address does not mark the document as outdated. Use
  the **Calculate US Tax** button on those documents.
- Rate data is not part of the fingerprint of a document: a new
  **Nexus**, **Tax Rate** or **Tax Rule** does not mark existing
  documents as outdated. **Calculate US Tax**, confirming the sale order
  or posting the invoice is what applies it to them.
