# Treatment arm — support-lead with expertise entries

Role definition: `scaffolds/default/agents/support-lead.md` at `f9993e0`,
194 lines. Identical to the control plus the 82-line `## Expertise` section;
no lines removed. Ticket: `ticket-sup-4471.md`. Delivered as a prompt to a
general-purpose agent. Verbatim final message follows.

---

## Support Readiness Summary

**Ticket:** SUP-4471 — Meridian Freight (Enterprise, renewal in 6 weeks, CSM-flagged at-risk)

### Symptom

- Reporter states shipment weights appear as dates in exported CSVs; three "bad files" this month.
- What is actually confirmed: a customer-side interpretation of the file. Nobody has yet looked at a raw export.
- Business impact is the concrete part: the team is re-keying by hand, hours per day, with a month-end close on the 30th.

**Facts vs. hypotheses (keep separate):**

| Item | Status |
|---|---|
| Numeric fields render as dates when the file is opened | Reported, not reproduced by us |
| A team member changed the regional format setting "a few weeks back" | Reported by the customer, unverified |
| Platform release shipped 11 days ago | Fact |
| KI-388 opened 3 weeks ago; 14 tickets closed against it | Fact |
| "It started after your last update" | Reporter's causal attribution, not an observation |

The timeline attribution does not hold up on its face: the release is 11 days old, KI-388 predates it by roughly 10 days, and the customer's own regional-format change is "a few weeks back." At least three candidate start points sit inside the same window, and "three bad files this month" is consistent with any of them.

### Live hypotheses

1. **KI-388 as written** — unquoted numeric fields, Excel locale coercion on direct open. Matches the symptom shape and the recent ticket volume.
2. **The regional format change** — decimal/thousands separator or date-order change on the customer's machines, altering how the same unchanged export parses. The reporter dismissed this ("that shouldn't matter"); it is the single most specific state change in the report and it is unverified.
3. **A genuine export-side regression in the 11-day-old release** — different from KI-388, presenting the same way. This is the one that gets buried if we close on the match.
4. **Field-level data corruption** — actual wrong values rather than misrendered ones. Currently unsupported by evidence, but "numbers come through wrong" is broad enough that it has not been excluded either. The word "corrupting" in the subject line is the reporter's interpretation, not a finding.

Note on hypothesis 1: KI-388 is the failure mode we have seen 14 times in the last month, which is exactly why it should be discounted rather than favored until we have the distinguishing observation. Volume tells us what is common, not what is happening here. The distinguishing observation is the raw file: under KI-388 the bytes on disk are correct and only the render is wrong. Under 3 or 4, the bytes are wrong.

### Diagnosis

Do not send the KI-388 workaround as the first reply. It resolves hypothesis 1 and hides 2, 3, and 4 behind an apparent fix — and if the real cause is 3, we will have closed a regression report as a known issue during a renewal window.

1. **Get the raw file.** Ask for one unmodified export that shows the problem, sent as an attachment, plus a screenshot of the same file open in their tool with a bad row visible. Open it in a plain text editor on our side. This single step separates render-layer (1, 2) from data-layer (3, 4).
2. **Take the last-occurrence account, not the summary.** Ask Dana or the person who hit it most recently: when was the last time you saw a bad file, what were you doing right before, what did you see on screen, what did you do next, which application opened it. Open questions only — do not ask "were you opening it directly in Excel?", which hands them the answer we are trying to test.
3. **Establish the real start date.** Ask for the oldest known-good export and the oldest known-bad one, by filename and date. Compare against the release date (11 days) and the reported regional-format change. If bad files predate the release, hypothesis 3 weakens sharply.
4. **Pin down the regional change.** What setting, on which machines, changed to what, and on what date. Ask neutrally as environment-gathering, not as the suspected cause.
5. **Reproduce internally.** Export the same report type against a comparable account, inspect the raw bytes, then open it under the customer's stated locale.

Do not treat the customer's dismissal of the regional change as evidence. They flagged it themselves — that is a cooperative reporter volunteering a state change, and it is the most actionable detail in the ticket.

### Resolution

**Workaround (offer only after step 1 confirms the file's bytes are correct):**
- Import via Data > From Text rather than opening the file directly, setting the affected columns to Text/Number explicitly. This is the KI-388 workaround and it addresses a render-layer problem only.
- If the regional setting turns out to be involved, reverting it on the affected machines may be faster than the per-import route for a team doing this daily.

**If the raw file contains wrong values:** there is no workaround. Stop, escalate immediately, and tell the customer we have confirmed a data-side defect. Do not offer the import workaround, which would mask it.

**Permanent fix path:** quote numeric fields on export, or emit a UTF-8 BOM plus explicit typing, so the export does not depend on the consumer's locale. This is an engineering change and belongs in the backlog regardless of which hypothesis wins — 14 closed tickets in a month means the current behavior is generating support load on its own.

### Escalation

**Escalate now, in parallel with diagnosis** — do not wait for the file. Two independent reasons: at-risk enterprise account with a hard month-end deadline on the 30th, and an unexcluded possibility of a regression in an 11-day-old release.

**Escalate immediately and upgrade severity if:** the raw file shows incorrect values rather than correct values rendered wrongly, or the first bad file postdates the release.

**Include in the escalation packet:**
- Observed: three reported bad files this month; weights displayed as dates; no sample obtained yet; not reproduced internally.
- Reproduced: nothing, as of this writing. State this plainly rather than letting the report read as confirmed.
- Believed, with basis: KI-388-class locale misinterpretation is plausible on symptom shape and recent volume — plausibility only, no file inspected.
- Ruled out: nothing yet. No observation has excluded any of the four hypotheses.
- Open: real start date; whether the regional format change is causal; whether the 11-day-old release altered export formatting; whether values or only rendering are affected.
- Context: Enterprise, renewal in 6 weeks, CSM-flagged at-risk, month-end close on the 30th.

Lead the packet with the observations, not with KI-388. If the escalation opens on the known issue, the next engineer will start from that label and investigate forward from it rather than from the evidence — and hypothesis 3 dies quietly at that point.

**Route to:** Engineering (export pipeline owner) as primary, with the release owner for the 11-day-old build copied given the timeline overlap. CSM notified given renewal risk. Product for the export-format finding below.

### Follow-ups

**FAQ / macro updates:**
- The KI-388 macro currently invites premature closure. Add a gate: do not send until a raw export has been inspected and confirmed byte-correct. Fourteen closures against this issue in a month is worth an audit — some fraction may be distinct defects filed under a convenient label.
- Add a standard intake block for export tickets: raw file attached, opening application, OS locale and regional settings, oldest known-good and known-bad file dates.

**Product / engineering feedback:**
- The export produces files whose correctness depends on the consumer's locale settings, and the product gives no warning of this. Dana's team changed a regional setting and had no reason to connect it to export integrity — nothing in the interface, the export dialog, or the docs suggests a link. That mismatch is a product finding, routed to discovery; it is not a customer mistake, and the case should not be framed that way in any internal note. The customer disclosing the change is the reason we have a second hypothesis at all.
- Candidate backlog items: quote numeric fields on export; add an "Export for Excel" option with explicit typing; surface a note in the export dialog when the file may be locale-sensitive.
- Recurring-issue signal: KI-388 has been open three weeks with 14 closures and a workaround as the only remedy. Workaround volume at that rate is the argument for prioritizing the permanent fix.

**Immediate action for the assigned agent:** reply to Dana today requesting the raw file and the last-occurrence account, acknowledge the 30th as a hard date, and confirm the escalation is already open. Do not send the workaround in that first reply.
