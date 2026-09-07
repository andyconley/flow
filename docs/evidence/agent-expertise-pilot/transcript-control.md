# Control arm — support-lead without expertise entries

Role definition: `scaffolds/default/agents/support-lead.md` at `main` (d232925),
112 lines. Ticket: `ticket-sup-4471.md`. Delivered as a prompt to a
general-purpose agent. Verbatim final message follows.

---

## Support Readiness Summary

**Ticket:** SUP-4471 · High · Enterprise, at-risk renewal in 6 weeks · Hard deadline: month-end close on the 30th

### Symptom

- Customer opens an exported shipment CSV and sees numeric fields rendered as dates — e.g. a shipment weight showing as a calendar date. Reported across three files this month.
- The data in the file is almost certainly intact. What the customer is seeing is Excel's type-guessing on unquoted numeric fields when the file is opened directly, matching known issue KI-388 (14 tickets closed against it in the last month).
- Support should recognize this instantly from the phrase "numbers show up as dates." That is Excel's signature, not a corrupted export.
- Normalize this in the docs: "corrupted export" is the natural way a user describes it, and it is not what is happening. Do not correct the customer's wording before you have confirmed it with a file.

Two things in this ticket cut against the customer's own diagnosis, and both matter:

- The customer says it started after the last update. The last release shipped 11 days ago; KI-388 was opened 3 weeks ago. The behavior predates the release. Treat "started after the update" as unverified.
- The customer mentions a regional format change on their side "a few weeks back" and dismisses it. That timing lines up with the reports far better than the release does, and locale is exactly what drives Excel's date coercion in KI-388. This is the strongest lead in the ticket, and the customer has already told you to ignore it.

### Diagnosis

1. **Get a sample file.** Nothing else moves until you have one. Ask for one of the three bad exports, unmodified, sent as an attachment — not pasted, not re-saved from Excel, since saving through Excel bakes in the misinterpretation and destroys the evidence. Also ask what the affected fields should have read.
2. **Open the raw file in a text editor, not Excel.** If the weight column contains the correct numeric values, the export is fine and this is a rendering problem at the customer's end. That single check separates KI-388 from an actual export defect and should take under a minute.
3. **Pin down the regional format change.** Which setting was changed, to what, on which machines, and on what date. Compare that date to the first bad file. Confirm whether the affected users share that configuration and whether anyone on a different setting sees clean files.
4. **Check the release timeline against their file dates.** Get the creation dates of all three bad files. If any predates the release 11 days ago, the update is ruled out as the cause and you can say so with evidence rather than assertion.
5. **Confirm how they open the files** — double-click versus Data > From Text — and whether all three files came from the same export path and template.

False leads to avoid: do not start by auditing the export pipeline or escalating to engineering on the strength of "it started after your update." Do not accept the customer's dismissal of the regional setting. And do not close this as a duplicate of KI-388 before step 2 confirms the raw values are correct — 14 prior closures make it tempting to pattern-match, and this ticket carries an at-risk renewal.

### Resolution

- **Workaround:** Import via Data > From Text (Get Data > From Text/CSV in current Excel) and set the affected columns to Text or Number explicitly at the import step rather than letting Excel infer. This is the documented KI-388 workaround and it works today, ahead of the 30th. Walk their team through it live rather than sending a doc link — they are re-keying by hand, so an unread doc costs them another day. Confirm it against one of their real files on the call.
- **Also worth checking:** whether reverting the regional format setting restores the old behavior on affected machines. Useful as confirmation of cause, but do not present it as the fix — the export should be robust regardless of the customer's locale.
- **Permanent fix path:** Quoting numeric fields in the export, or emitting a format Excel does not re-type on open. This is engineering work under KI-388 and will not land before the 30th. Do not imply otherwise to the customer.

### Escalation

- **Escalate when:** step 2 shows the raw file values are wrong — that is a genuine export defect, separate from KI-388, and it goes to engineering immediately at high priority. Escalate on the KI-388 path as well, because 14 closures plus an at-risk enterprise renewal makes the volume argument that the underlying fix needs a date.
- **Include:** the raw sample file; the specific field, expected value, and displayed value; the exact regional format setting, its previous value, and the change date; creation dates of all three bad files; the platform version at export time; Excel version and OS; whether the workaround resolved it on their real data; and the KI-388 ticket count with this account's renewal status.
- **Route to:** engineering owns the KI-388 fix and any confirmed export defect. Product owns the prioritization call, given ticket volume against a customer-visible data-integrity issue. Loop in the CSM now, not after — the renewal is 6 weeks out and flagged at-risk, and their team is absorbing hours a day of manual work.

### Follow-ups

- **FAQ / macro updates:** Add an FAQ entry keyed on the customer's own words ("numbers showing as dates," "export is corrupting data") rather than on the technical cause, so it is findable by the people who need it. Build a macro carrying the import steps and the request for a raw unmodified sample. Add "ask for the raw file before diagnosing" to the export-issue checklist — this ticket sat without one.
- **Product or engineering feedback:** 14 tickets in a month against a workaround, not a fix, is the argument for prioritizing KI-388. Locale-dependent export behavior deserves either quoted numeric output by default or a documented locale-safe export option. Worth flagging separately: customers are attributing this to the recent release when the issue predates it. Left uncorrected, that misattribution will attach itself to future releases too.

**Immediate next action:** request the raw sample file and the regional-setting details, and offer a live walkthrough of the import workaround so their team can stop re-keying before the 30th.
