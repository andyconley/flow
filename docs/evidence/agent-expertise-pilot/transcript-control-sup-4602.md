# Control arm (counter-test) — support-lead without expertise entries

Role definition: `scaffolds/default/agents/support-lead.md` at `main` (d232925),
112 lines. Ticket: `ticket-sup-4602.md`. Delivered as a prompt to a
general-purpose agent pointing at the definition and ticket files; both arms of
this run received the identical delivery. Verbatim final message follows.

---

## Support Readiness Summary

### Symptom
- User opens the shipment CSV export by double-clicking it in Excel. The weight column shows `12. Apr` instead of `12.4`. Other columns look normal.
- Only affects users whose Excel locale uses a comma decimal separator (de-DE, fr-FR, nl-NL, etc.). In those locales Excel reads the period in `12.4` as a date separator and silently autoconverts.
- Nothing is wrong with the data. The file on disk contains `12.4`. This is a rendering conversion inside Excel, not an export defect.
- Normalize this in the docs: users reliably read it as data corruption and describe it as "wrong numbers in the export." Expect the phrase "the export is broken."

### Diagnosis
1. Open the attached file in a plain text editor (Notepad, VS Code) and read the raw row. If it reads `SHP-88214,Rotterdam,12.4,2026-08-28`, the export is correct and the problem is entirely Excel-side. Stop here — this is KI-388.
2. Confirm the user's Excel locale/regional format setting. Comma-decimal locale plus double-click open is the signature.
3. Confirm how the file was opened. Double-click open triggers the autoconversion; `Data > From Text/CSV` with the column typed as Text does not.

False leads to avoid:
- Do not chase the platform release. Last release shipped 40 days ago, reported onset was 6 days ago. The timing does not line up and the export format did not change.
- Do not treat "it worked on my old machine last month" as evidence of a regression. A fresh Excel install loses the previous machine's saved import preferences and any prior column-type choices, so the same file now opens through the default path instead of the one that used to work. The machine changed; the file did not.
- Do not ask for a re-export. A new export produces the identical bytes and the identical rendering.

### Resolution
- **Workaround (customer, immediate):** Do not double-click the file. In Excel: `Data > From Text/CSV`, select the file, set the weight column type to **Text**, then Load. The value renders as `12.4`. This is the documented KI-388 workaround and it works today with no changes on our side.
- **Second option:** rename the file extension from `.csv` to `.txt` before opening, which forces Excel to show the import wizard rather than autoconverting.
- **Not a fix and do not recommend:** changing the user's Windows regional settings. It resolves the symptom but breaks every other locale-dependent thing on their machine.
- **Permanent fix path:** engineering change to the exporter — quote numeric fields, or emit a locale-safe format. Owned by KI-388, already open. No customer action will make double-click open work correctly until that ships.

### Escalation
- **Do not escalate this ticket.** It is a confirmed instance of an existing known issue with a working workaround, internally reproduced, on a self-serve single-seat account with no renewal event pending. Answer it directly with the workaround and close against KI-388.
- **Escalate only if:** the raw file contents do not match what the user reports (meaning the export really is producing bad values), or the `Data > From Text` workaround fails to render `12.4`. Either would mean this is not KI-388.
- **If escalating, include:** the raw line from the attached file, the user's Excel locale, the open method used, the result of the From Text import attempt, and the export timestamp.
- **Route to:** the engineering owner of KI-388. Not SRE — there is no availability or platform-health component here.

### Follow-ups
- **FAQ / macro updates:** This is the 15th ticket against KI-388 in a month, and the ticket count is the story. Two things are missing that the volume justifies:
  - A support macro for KI-388 with the From Text steps written out click-by-click, so the workaround is not retyped per ticket.
  - A public help-center entry titled around what the user actually searches for — "weights show as dates in Excel" — not around the internal cause. Tomas searched and did not find it, which is why this became a ticket instead of a self-serve fix.
- **Add to the reply:** tell Tomas plainly that his file is correct and his data is intact. He asked "is there a setting I should change on my side?" and the honest answer is that the setting is not his to change — this is on our export and a fix is tracked. Say that. A self-serve user who is told to permanently change his import habits without explanation reads it as being brushed off.
- **Product / engineering feedback:** 14 closed tickets plus this one in a month against a rendering bug with a known one-line fix is a poor trade. The workaround is not free — it costs the user a multi-step import every single time, forever, and costs support a ticket for each user who hits it before finding the docs. Worth raising KI-388's priority with the ticket count attached as the argument.
- **Documentation gap worth tracking:** the export docs do not mention Excel locale behavior at all. A short note at the point of download, next to the export button, would intercept this before it becomes a ticket.
