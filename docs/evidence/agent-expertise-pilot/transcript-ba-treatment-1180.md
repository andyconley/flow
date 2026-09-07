# Treatment arm — business-analyst with expertise entries

Role definition: `scaffolds/default/agents/business-analyst.md` at `f9993e0`,
211 lines. Request: `request-ba-1180.md`. Delivery identical to the control.
Verbatim final message follows.

---

## Problem Statement

- **What:** Invoices we issue in-country must display the supplier's tax registration number, labeled "Supplier TRN", on the face of the invoice PDF and in the invoice API response. *(Observed — Notice 2026/14 §4.2; Legal determination.)*
- **Who:** The obligation is ours as issuer. The party who feels a failure is the recipient (an invoice missing a mandated field may be rejected or non-deductible for them) and Finance, who absorbs the reissue. *(Inferred — the notice states the display requirement; it does not state the consequence of omission.)*
- **Why now:** Fixed external deadline of 1 January 2027. No ramp, no partial compliance. *(Observed.)*

The request names a field, and in this case the job behind it is the same size as the field: display a value we already hold, on documents we already generate, by a date. There is no larger unmet need hiding underneath. Recording that explicitly so the next role does not go looking for one.

## Users and Workflows

- **Primary personas:** Finance/Controller (accountable for compliance); invoice recipient (reads the PDF); API consumers integrating invoice data.
- **Current workflow:** Invoice is generated; supplier block renders without a TRN; API returns the invoice payload without a TRN.
- **Future workflow:** Identical, with the TRN rendered in the supplier block and present in the API payload for in-scope invoices. No new steps, approvals, or data entry. Finance already holds the TRN for every in-country supplier. *(Observed — stated in the request.)*

## Scope

- **In scope:** TRN display on the invoice PDF; TRN in the invoice API response; the rule that decides whether a given invoice is in scope.
- **Out of scope:** Backfill or reissue of invoices dated before 1 Jan 2027 *(Observed — Legal: not retroactive)*; any TRN collection or maintenance workflow *(Observed — data complete)*; TRN display on invoices not issued in-country; validating the TRN against the revenue authority.
- **Constraints:** Label must read "Supplier TRN". Format is 2 letters followed by 9 digits. Must appear on the face of the invoice. Placement is unspecified by the rule and is ours to choose. Hard date: invoices issued on or after 1 Jan 2027.

## Requirements

**Goals**

1. Every in-scope invoice displays the supplier TRN with the mandated label on the face of the PDF.
2. Every in-scope invoice API response includes the supplier TRN.
3. Out-of-scope invoices are unchanged.

**Non-goals**

- Changing any other invoice content, layout beyond accommodating the new line, or numbering.
- Format-validating or normalizing TRN values as part of this change *(see open question 3 — this may move into scope)*.

**User stories**

- As an invoice recipient, I can see the supplier's TRN on the invoice I receive, so the invoice is valid for my own tax filing.
- As an API consumer, I can read the supplier TRN from the invoice response without parsing the PDF.
- As the Controller, I can confirm that invoices issued from 1 Jan 2027 carry the TRN and that earlier invoices were not altered.

**Acceptance criteria**

1. An invoice issued on or after 1 Jan 2027 that is in-country renders "Supplier TRN" and the value on the face of the PDF, on the first page, visible without scrolling past the itemized lines.
2. The same invoice's API response contains the TRN. *(Field location deferred — see open question 1.)*
3. An invoice issued before 1 Jan 2027 renders and returns exactly as it does today; a byte-comparable regeneration of a pre-2027 invoice shows no change.
4. An invoice not issued in-country renders and returns as it does today.
5. An invoice dated 1 Jan 2027 is treated as in scope; 31 Dec 2026 is not.

**Not yet defined:** the behavior when a supplier record has no TRN, or holds a value that does not match the 2-letters-plus-9-digits format, at render time. The options — block issuance, render blank, or render as-is — differ in consequence, and choosing between them needs evidence Finance holds (open question 3), not a judgment call from the delivery team. Everything else here can proceed without it.

## Risks and Open Questions

**Risks**

- The in-scope test is the only real logic in this change, and it is the part most likely to be wrong quietly — a wrong answer produces correct-looking invoices that are non-compliant, or retroactive changes to closed invoices. It deserves more test attention than the rendering.

**Assumptions** *(each with what would settle it)*

1. "Issued in-country" maps cleanly to an existing attribute on the invoice or supplier record. — Confirm with whoever owns the invoice data model; if it does not, this request is larger than it appears.
2. "Issued on or after 1 Jan 2027" maps to an existing invoice date field with a single, unambiguous meaning. — Confirm which date (creation, issue, posting) Legal's determination refers to, with Legal or Priya.
3. TRN values are complete *and* conform to the mandated format. Finance stated completeness; format conformance was not stated and does not follow from it. — Run the stored in-country TRNs against the format and count exceptions.

**Open questions**

1. `supplier` object vs. top-level API field — with the API owner, expected this week. Does not block PDF work.
2. Placement on the PDF — ours to decide since the rule is silent. Needs one decision from Finance/design, not an investigation.
3. Do any stored in-country TRNs fail the format check, and if so, what should the invoice do? — Finance can answer the first half from data this week; the answer determines the second half.
4. Do credit notes, corrections, or reissues of a pre-2027 invoice count as invoices "issued" in 2027? Legal's determination addresses original issuance and does not speak to these. — Legal.

## Premortem

Assume this ships, meets every criterion above, and Finance is still non-compliant on 2 January 2027. The reasons that survive scrutiny:

- The in-scope date used a different date field than the one Legal meant, so a band of December/January invoices fell on the wrong side.
- A subset of suppliers had TRNs stored in a format the authority rejects; the field displayed, but with an invalid value.
- Credit notes issued in 2027 against 2026 invoices were treated as out of scope, and the authority disagreed.

All three are already carried above — as assumptions 2 and 3 and open question 4. None of them is a rendering problem, which is where the effort would naturally go.

## Delivery Slices

1. **Settle the three deciders.** Confirm the date field and the in-country attribute; run the format check over stored TRNs. Small, and everything downstream depends on it.
2. **PDF.** Render the labeled field for in-scope invoices, with the placement decision made. Independently valuable — this is the face-of-invoice obligation the rule actually states.
3. **API.** Add the field once the owner answers question 1. Sequenced after the PDF only because it has an unresolved dependency, not because it matters less.

Handling for missing or malformed TRNs attaches to slice 2 or 3 once open question 3 is answered; if the exception count is zero, it disappears.

---

Two prior invoice-field additions shipped in under a sprint each, and nothing here suggests this one is different in size. The work worth doing before building is slice 1, and it is a few conversations, not a discovery effort.
