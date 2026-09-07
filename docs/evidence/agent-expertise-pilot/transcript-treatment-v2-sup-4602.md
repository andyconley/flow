# Treatment v2 (counter-test) — support-lead with the sufficiency entry

Role definition: `scaffolds/default/agents/support-lead.md` with the sixth
entry, "Act when the distinguishing observation is already in hand", 214 lines.
Ticket: `ticket-sup-4602.md`. Delivery identical to the other arms of this run.
Verbatim final message follows.

---

## Support Readiness Summary

### Symptom
- In Excel (de-DE locale), the `weight` column of the shipment CSV export renders as dates: `12.4` displays as `12. Apr`. Other columns look correct.
- Reporter's framing — "a setting I should change on my side" and "started when IT gave me a new laptop" — is the reporter's own theory, not a finding. The new laptop is a timeline coincidence, not a demonstrated cause.

### Diagnosis
1. **Confirm the file, not the display.** Already done: Tier 1 read raw line 2 as `SHP-88214,Rotterdam,12.4,2026-08-28`. The exported value is correct. This is a rendering issue in Excel, not a data defect in the export. No further evidence needed from the reporter on this point.
2. **Confirm the rendering path.** Already done: internal repro on the same file, Excel at de-DE, opened by double-click, reproduces the date rendering; the same file imported via Data > From Text with column type Text renders `12.4`. Double-click open is the distinguishing variable, not the machine.
3. **Distinguish this from the recent cluster before applying the macro.** KI-388 is the pattern being matched, and 14 tickets closed against it in the last month make it the first thing that comes to mind. The distinguishing observation is already in the record: reported onset was 6 days ago, and the last platform release shipped 40 days ago. No export-side change can have caused an onset inside that window. What did change 6 days ago was the reporter's machine — a fresh Excel install with default de-DE regional settings, where the old machine likely carried non-default settings. That is consistent with KI-388's rendering mechanism, not with a new defect.

**False leads to avoid:** treating the new laptop as a hardware or install fault; asking the reporter to re-send the file or re-check the value (the raw line is already in the record); chasing a recent-release regression (the release timeline excludes it).

**Signal that would reopen this:** a de-DE reporter who sees the date rendering *after* importing via Data > From Text with column type Text, or a raw file where the weight field genuinely contains a date. Either breaks the KI-388 mechanism and means a distinct defect.

### Resolution
- **Workaround (customer action, safe, immediate):** Do not double-click the CSV. In Excel: Data > From Text/CSV, select the file, set the weight column type to Text (or set the locale/data origin in the import dialog to match the file), then Load. Values render as `12.4`. This is the KI-388 workaround and it is confirmed against this exact file.
- **Permanent fix path:** Engineering — quote numeric fields in the CSV export, or emit a locale-explicit format, so a plain double-click open is safe. Tracked under KI-388. This ticket does not need its own engineering escalation.

### Escalation
- **Escalate when:** the reopening signal above appears, or the ticket count against KI-388 keeps climbing past the current 14/month.
- **Include if escalating:** the raw CSV line, the Excel locale, and both open paths tried (double-click vs. From Text) with the rendering each produced. State beliefs with their basis — do not lead with "CSV export bug", which sends the next person to the exporter when the exported bytes are correct.
- **Route to:** No engineering escalation on SUP-4602. Resolve with the workaround. Route the volume signal (below) to product; this is a single self-serve seat with no renewal event and no prior tickets, so the individual case does not warrant carrying an open question further.

### Follow-ups
- **FAQ / macro updates:**
  - Add a macro for KI-388 that opens by naming what the reporter actually sees (`12.4` shown as `12. Apr`) rather than the internal cause, states plainly that the exported data is correct and only the display is wrong, and gives the From Text steps. Reporters searching for their symptom will not search for "unquoted numeric field".
  - Add an FAQ entry under exports: "My export opens with wrong numbers/dates in Excel." Normalize it — this is expected behavior of Excel's double-click import under several European locales, not a corrupted file, and not something the reporter configured wrong.
  - Note in the macro that a machine change is a common and reasonable-sounding trigger to report, because a fresh Office install resets regional import defaults. Tier 1 should not spend time on the machine.
- **Product or engineering feedback:**
  - **Volume, not severity, is the argument.** 14 tickets in a month against a rendering issue with a known workaround is a standing support tax on the most common thing users do with an export. Raise KI-388's priority on that basis.
  - **The affordance is the defect, not the user's action.** Double-clicking a `.csv` is what the file type invites and what every OS default does; nothing in the export or the download UI signals that this path corrupts the display. The reporter did the obvious thing and then blamed themselves ("a setting I should change on my side"). Route to discovery: the product currently ships a file whose default open path is wrong for a large locale group, and the burden of knowing that falls on the user.
  - Candidate requirement for the export work: a CSV export must render correctly on a plain double-click open in Excel under at least de-DE, fr-FR, and en-US locales. Quoting numeric fields is the cheap version; offering an `.xlsx` export option is the version that removes the class of problem.
  - Documentation gap worth writing as acceptance criteria: the export download page has no note about Excel import behavior at all. A single line at the download point would intercept most of these tickets before they are filed.
