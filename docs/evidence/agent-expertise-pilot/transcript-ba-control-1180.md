# Control arm — business-analyst without expertise entries

Role definition: `scaffolds/default/agents/business-analyst.md` at `main`
(d232925), 130 lines. Request: `request-ba-1180.md`. Delivered as a prompt to a
general-purpose agent pointing at the definition and request files; both arms
received identical delivery. Verbatim final message follows.

---

## Problem Statement
- **What:** Invoices issued in-country do not display the supplier's tax registration number. Notice 2026/14 §4.2 requires it on the face of every invoice issued on or after 1 Jan 2027. It also needs to be present in the invoice API response.
- **Who:** Finance/Controller function owns the compliance exposure. Recipients of in-country invoices are the audience for the displayed field. API consumers who read invoice data are secondary.
- **Why now:** Fixed external deadline of 1 Jan 2027. Non-compliance is a regulatory matter, not a preference.

## Users and Workflows
- **Primary personas:** Controller (compliance owner), invoice recipient (reader of the PDF), API consumer (reads invoice response).
- **Current workflow:** Invoice is generated; PDF and API response omit the supplier TRN. Finance holds the TRN separately in its own records.
- **Future workflow:** Unchanged except that invoices issued on or after the effective date render "Supplier TRN" on the face of the PDF and expose the same value in the API response. No new data collection step, no new approval step.

## Scope
- **In scope:** Displaying the supplier TRN on the invoice PDF; exposing it in the invoice API response; applying it to invoices issued on or after 1 Jan 2027 for in-country suppliers.
- **Out of scope:** Backfill or reissue of invoices dated before 1 Jan 2027 (Legal determined no retroactive application). Any TRN collection, entry, or verification workflow (Finance data is complete). Validation of TRN correctness against the authority. Out-of-country invoices. Any other customer-facing behavior change.
- **Constraints:** Label text must be "Supplier TRN". Format is 2 letters followed by 9 digits. The field must appear on the face of the invoice; placement is not specified by the rule and is ours to choose.

## Requirements
- **Goals:**
  1. Every in-country invoice issued on or after 1 Jan 2027 shows the supplier TRN on the PDF face under the label "Supplier TRN".
  2. The same value is available in the invoice API response.
- **Non-goals:** Historical backfill; TRN capture UI; format enforcement at data-entry time; changes to invoice numbering, totals, or delivery.
- **User stories:**
  - As an invoice recipient, I see the supplier's TRN on the invoice so the document satisfies the revenue authority's requirement.
  - As an API consumer, I can read the supplier TRN from the invoice response without fetching it from another endpoint.
  - As the Controller, I can confirm that invoices issued before the effective date are unchanged.
- **Acceptance criteria:**
  - An in-country invoice with issue date on or after 2027-01-01 renders the literal label "Supplier TRN" and the supplier's TRN value on the face of the PDF.
  - The rendered value matches the format `[A-Z]{2}[0-9]{9}`.
  - An invoice with issue date before 2027-01-01 renders exactly as it does today — no TRN field, no layout shift.
  - The invoice API response for a post-effective-date in-country invoice contains the TRN, and its value is identical to the value printed on the PDF for the same invoice.
  - The added field does not displace or overlap existing required invoice content at the chosen placement.
  - Boundary check: an invoice issued at the first instant of 2027-01-01 in the governing time zone includes the field.

## Risks and Open Questions
- **Risks:** Low. The main risk is the API shape decision landing late and forcing rework of consumer-facing contract or docs. Secondary risk is a PDF layout collision at the chosen placement.
- **Assumptions:**
  - *Stated as fact by the requester, not re-verified here:* Legal's interpretation, the completeness of Finance's TRN data, and the no-backfill determination.
  - *Assumed by me:* "In-country" is determinable from existing invoice data without a new flag. The issue date already drives which template version renders. The governing time zone for the 1 Jan 2027 boundary is the in-country one.
- **Open questions:**
  1. `supplier` object vs. top-level API field — already with the API owner, answer expected this week. This is the only blocker, and only for the API slice.
  2. Which time zone governs the effective-date boundary (my assumption above needs a one-line confirmation from Finance).
  3. If a supplier's TRN is somehow absent at render time, does the invoice fail to issue or render without the field? Finance says data is complete, so this is an exception path, but the behavior should be decided rather than defaulted.

## Delivery Slices
1. **PDF field.** Render "Supplier TRN" on the face of the invoice, gated on issue date >= 2027-01-01 and in-country. Ships independently and covers the "face of the invoice" requirement, which is the part the rule is explicit about. Not blocked by the open API question.
2. **API field.** Add the TRN to the invoice response once the API owner rules on placement. Same date and locale gating; value sourced identically to the PDF so the two cannot diverge.
3. **Follow-on (optional).** Missing-TRN exception handling per open question 3, if Finance wants a defined behavior rather than relying on data completeness.

Two prior invoice-field additions shipped in under a sprint each, and nothing here indicates this one is harder — the data exists, the rule is explicit, and the only unresolved item is scoped to slice 2 and expected this week. I would not size this above those precedents.
