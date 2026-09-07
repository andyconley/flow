# Treatment arm (counter-test) — support-lead with expertise entries

Role definition: `scaffolds/default/agents/support-lead.md` at `f9993e0`,
194 lines. Ticket: `ticket-sup-4602.md`. Delivered as a prompt to a
general-purpose agent pointing at the definition and ticket files; both arms of
this run received the identical delivery. Verbatim final message follows.

---

## Support Readiness Summary

### Symptom
- Weight column in the shipment CSV export renders as dates in Excel: `12.4` displays as `12. Apr`. Other columns look normal. Reporter's locale is de-DE, single self-serve seat.
- Reporter's framing is "is there a setting I should change on my side?" — they already suspect themselves. The export file is correct; raw line 2 reads `SHP-88214,Rotterdam,12.4,2026-08-28`. This is a rendering behavior in Excel, not a data defect in the export.
- Support should recognize this by the pattern "decimal number becomes day-month" plus a comma-decimal locale (de-DE, fr-FR, nl-NL, pt-BR and similar). Normalize this in docs: the file is not corrupted, and nothing was lost.

### Diagnosis
1. Open the attached file in a text editor (not Excel) and read the raw line for the affected row. Confirm the numeric value is intact and unquoted. Tier 1 already did this here — value is `12.4`, correct.
2. Ask the reporter for the last occurrence in specifics, not a summary: what they did the last time it happened — how they opened the file (double-click from Downloads, File > Open, drag into an open workbook, or Data > From Text), what the weight cell showed, and what the formula bar showed for that cell. Do not ask "did you double-click it?" — that supplies the answer, and their account is the only evidence we have of the new-laptop difference.
3. Establish what changed between the old laptop and the new one. Ask them to check, on the new machine, Excel's regional/locale setting and Data > Get Data > Data Options for CSV import defaults, and compare against the old machine if it is still available. This is the observation that separates the two live hypotheses below.

**Do not stop at step 1.** The file being correct proves the export is not at fault; it does not identify why this reporter is now affected and was not last month.

### Live hypotheses (keep both open)

- **H1 — KI-388, matched on symptom.** Excel misinterprets unquoted numeric fields as dates for some locales. Reproduced internally: same file, Excel at de-DE, opened by double-click, renders as dates; imported via Data > From Text as Text, renders `12.4`. Basis: internal reproduction.
- **H2 — the new laptop's Excel configuration, not the export.** Basis: the reporter's timeline does not fit KI-388 alone. The last platform release shipped 40 days ago; reported onset is 6 days ago and coincides exactly with a fresh Excel install on new hardware. The same export opened correctly on the old machine last month. Nothing on our side changed in that window. A default open-behavior or locale difference between the two Excel installs would explain the change in timing that KI-388 by itself does not.

KI-388 has 14 tickets closed against it in the last month, which is exactly the condition under which a resembling report gets absorbed into the known issue and a distinct cause disappears. The distinguishing observation is the timeline, and step 3 is what takes it. Take step 3 before closing against KI-388.

Ruled out so far: export-side data corruption — ruled out by the raw file read (`12.4` present and correct).

### Resolution
- **Workaround (safe, customer-side, works today):** import via Data > From Text/CSV and set the weight column type to Text (or Locale: English (United States) in the import dialog's Data Type Detection). Verified internally against this exact file. Give them the click path, not just the feature name. This addresses the display for them regardless of which hypothesis holds.
- **Permanent fix path:** engineering-side quoting of numeric fields in the export, tracked under KI-388. Do not promise a date to the reporter.
- **Requires engineering:** the export-format change. Nothing here requires an operator action on the account.

### Escalation
- **Escalate when:** step 3 shows the new laptop's Excel locale and CSV import defaults match the old machine's — that rules out H2 and leaves an unexplained onset. Also escalate if the reporter confirms the old machine still renders the same file correctly today.
- **Include, stated separately:** raw line 2 as read from the file (`SHP-88214,Rotterdam,12.4,2026-08-28`) and the confirmation that the exported value is correct; the internal reproduction and its exact conditions (de-DE locale, opened by double-click — fails; Data > From Text with column type Text — renders 12.4); the timeline mismatch (release 40 days ago, onset 6 days ago, coincident with new laptop and fresh Excel install, same export fine on old machine last month); both hypotheses above with their bases; what was ruled out and by which observation (export-side corruption, by the raw file read); and what is still open (why onset tracks the laptop change rather than any platform change).
- **Do not lead the packet with "KI-388."** With 14 recent closures, a packet headed by that label will be read as confirmed and closed without the timeline being examined.
- **Route to:** engineering, on the KI-388 thread, but flagged as a timeline anomaly rather than a duplicate closure.

### Follow-ups
- **FAQ / macro updates:** publish a short FAQ entry — "Numbers in my export show as dates in Excel" — covering what the user sees, the statement that the file itself is correct, the Data > From Text click path with a screenshot, and which locales are affected. The reporter found no such entry and opened a ticket asking whether they were at fault; 14 prior closures suggest others did the same.
- **Product or engineering feedback:** quote the numeric fields in the export. The current behavior costs a support contact per affected user and puts the burden on them to discover a non-obvious Excel import path. This is a product finding, not a user error — the export gives no signal that double-clicking will misread it, and double-click is the default affordance for a `.csv` attachment. That mismatch belongs in discovery regardless of what we tell this reporter.
- **Backlog candidates:** (a) export numeric fields quoted, or offer an `.xlsx` export option; (b) a locale note in the export UI or the download confirmation; (c) instrument how many KI-388-matched tickets arrive from comma-decimal locales, to size the fix.
- **Process note:** KI-388's high closure rate is now a triage risk. Suggest adding a line to the KI-388 known-issue entry: before closing a match, confirm the reported onset is consistent with a platform release, not with a client-side change.
