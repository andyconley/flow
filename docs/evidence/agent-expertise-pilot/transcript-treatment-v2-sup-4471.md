# Treatment v2 (trap ticket re-run) — support-lead with the sufficiency entry

Role definition: `scaffolds/default/agents/support-lead.md` with the sixth
entry, "Act when the distinguishing observation is already in hand", 214 lines.
Ticket: `ticket-sup-4471.md`. Delivery identical to the other arms.
Run to check that the sufficiency entry does not undo the SUP-4471 result.
Verbatim final message follows.

---

## Support Readiness Summary

### Symptom
- Shipment weights and other numeric fields appear as dates when Meridian Freight opens exported CSVs. Three bad files this month; team is re-keying by hand. Reporter attributes it to "your last update."
- Recognition cue for support: numeric column renders as a date (e.g. `12/5` or `5-Dec`) in a spreadsheet — this is display/parse behavior, not necessarily corrupted bytes in the file.

### Diagnosis
1. **Get the last occurrence, not the summary.** Ask Dana: which file, exported when, opened how (double-click vs Data > From Text), on which machine, and what the cell showed versus what it should have been. Request one of the three bad files plus, if possible, the raw file re-downloaded and opened in a plain text editor (Notepad/TextEdit) — text-editor view tells us in one step whether the bytes are wrong or only Excel's rendering is.
2. **Separate the two candidate causes and keep both alive.**
   - (a) KI-388: Excel auto-converting unquoted numeric fields to dates on open. Locale-sensitive, matches the symptom, 14 tickets closed against it.
   - (b) The regional format setting change the customer mentioned. Dana said "that shouldn't matter" — that is her interpretation, not an observation. A regional/locale change is exactly the variable KI-388 is sensitive to, and it is also capable of producing decimal-separator corruption (e.g. `1.234` read as `1234` or `1,234`) that is *real* data damage, not display-only. Do not let her dismissal close it.
3. **Test the timeline claim against the release.** Dana says it started after the last update; the platform release shipped 11 days ago, and KI-388 opened 3 weeks ago. Ask for the date of the first bad file. If bad files predate the release by more than a couple of days, the release is not the trigger and the format-setting change moves up. If they cluster after day 11, a release-introduced regression in the export path becomes live and KI-388 alone does not explain it.

**False leads to avoid:** treating KI-388 as confirmed because the symptom matches. This is the recently-seen, high-volume failure mode — 14 closures in a month is exactly the condition that makes it the first thing anyone reaches for. The distinguishing observations we do not yet have are the text-editor view of the file and the first-bad-file date. Until one of those lands, applying the KI-388 macro risks burying a distinct defect (a release regression, or genuine locale-driven numeric corruption) inside a case marked resolved.

**Note on the customer's format change:** this is not user error and should not be logged as such. If a regional setting inside the product can silently change how exported numbers are written, the product afforded that outcome — the operator had no way to see the consequence at the time they made the change. Dana volunteering it unprompted is high-value signal; treat it that way so she keeps volunteering.

### Resolution
- **Workaround (send now, framed as interim):** import via Data > From Text/Get Data, setting the weight and numeric columns to Text or the correct numeric type rather than General. This addresses cause (a) and unblocks the month-end close on the 30th. State plainly that this is a workaround while we confirm the cause, not a diagnosis — do not close the ticket on it.
- **Also send now:** a re-export of one recent dataset performed by support internally, so the customer has a known-good file to compare against and can stop re-keying while we investigate.
- **Permanent fix path:** quote numeric fields in the export writer, or emit a format Excel does not coerce. Owned by engineering under KI-388. If the file itself proves to contain wrong values (cause b or a release regression), that is a separate defect and needs its own ticket — KI-388 does not cover data written incorrectly at source.

### Escalation
- **Escalate when:** the text-editor view shows wrong values in the raw file (immediate — this is data loss, not rendering), OR the first bad file postdates the release by less than 11 days with no format-setting overlap, OR we cannot get a sample file within 24 hours given the 30th deadline and at-risk renewal.
- Given High priority, a 6-week renewal flagged at-risk by the CSM, and a hard month-end deadline, escalate in parallel with evidence-gathering rather than after it. Loop the CSM in today.
- **Include in the escalation packet:**
  - *Observed:* numeric fields (shipment weights) displaying as dates; three files affected this month; customer re-keying by hand at hours/day cost.
  - *Reproduced:* [pending — state explicitly whether support reproduced it internally and under which locale, or that we have not yet].
  - *Currently believed:* KI-388 (Excel locale coercion on open) is the leading hypothesis — basis: symptom match and 14 prior closures. This is a match, not a confirmation; the distinguishing observation has not been taken.
  - *Not ruled out:* (1) the customer's regional format setting change, which is temporally plausible and could produce real numeric corruption rather than display-only; (2) a regression in the release 11 days ago. Neither has been excluded by any observation.
  - *Ruled out:* nothing yet.
  - *Open:* raw-file inspection, date of first bad file, export locale at time of export.
  - Do not lead this packet with "KI-388" as the subject line. The next owner will investigate from the label instead of from the evidence, and the two live alternatives will die in the handoff.
- **Route to:** Engineering (export writer, owner of KI-388) with the Release Engineering owner cc'd on the 11-day timeline question; CSM notified given renewal risk; Product for the regional-format-setting finding below.

### Follow-ups
- **FAQ / macro updates:**
  - Rewrite the KI-388 macro so it presents the Data > From Text step as an interim workaround and requires the raw-file check before the ticket can be closed. The current macro lets a match close a case without a distinguishing observation — 14 closures with that gap is worth an audit.
  - Audit those 14 closed tickets for any that mention a regional or locale setting change. If more than one or two do, the cluster is not all KI-388.
  - Add an operator-facing FAQ entry: "Numbers in my export look like dates" — covering what to check, what to send support, and how to tell display coercion from real corruption.
- **Product / engineering feedback:**
  - The regional format setting changes export output with no warning, no preview, and no visible link to downstream file format. That mismatch is a product finding, not a customer mistake — route to discovery. Candidate requirement: surface the export-format consequence at the point the setting is changed.
  - Export currently emits unquoted numeric fields. Quoting them (or offering an Excel-safe export option) removes the whole class of ticket. Backlog item with the 14+ ticket volume attached as justification.
  - Recurring-issue signal: numeric-as-date is now the single largest identifiable ticket cluster this month. Worth a standing note in release QA that export output be verified under at least one non-default locale.
