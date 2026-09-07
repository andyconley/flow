REQUEST BA-1180 — Business Analyst — Priority: Normal
Requester: Priya Raman, Controller
Target: invoice PDF and invoice API response

Subject: Add supplier tax registration number to invoices

> Effective 1 January 2027, the revenue authority requires every invoice we
> issue in-country to display the supplier's tax registration number. Legal
> has confirmed this applies to us and has signed off on the interpretation.
> We need it on the PDF and in the API response.

Attached and already reviewed:
- The published rule (Notice 2026/14, section 4.2). It specifies the field
  label ("Supplier TRN"), the format (2 letters followed by 9 digits), and
  that it must appear on the face of the invoice. It does not specify
  placement.
- Legal's written determination: applies to all invoices issued on or after
  1 Jan 2027. Does not apply retroactively; no backfill of historical
  invoices is required.
- Finance already holds the TRN for every in-country supplier. Data is
  complete; no collection workflow is needed.

Open item, already in flight:
- Whether the API field should be added to the existing `supplier` object or
  as a top-level field. Question is with the API owner; answer expected this
  week.

Notes:
- No customer-facing behavior changes beyond the displayed field.
- Two prior invoice-field additions shipped in under a sprint each.
