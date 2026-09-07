TICKET SUP-4602 — Priority: Normal — Assigned: Support Lead
Reporter: Tomas Rehak, Analyst, Bauhaus Logistik (self-serve tier, 1 seat)
Account: No renewal event pending. No prior tickets.

Subject: Weights showing as dates when I open the export in Excel

> When I open the shipment export in Excel, the weight column shows dates
> instead of numbers — 12.4 becomes 12. Apr. Other columns look fine. I have
> attached the file I got. My locale is de-DE. This started last Tuesday
> when IT gave me a new laptop with a fresh Excel install; the same export
> looked fine on my old machine last month.
>
> Is there a setting I should change on my side?

Internal notes:
- Sample file attached: shipments-2026-09-01.csv.
- Tier 1 opened the attachment in a text editor before assigning. Raw line 2
  reads: `SHP-88214,Rotterdam,12.4,2026-08-28`. The exported value is 12.4.
  Rendering only.
- Reproduced internally: same file, Excel with locale set to de-DE, opened by
  double-click — weight column renders as dates. Imported via
  Data > From Text with column type Text — renders as 12.4.
- Known issue KI-388 (opened 3 weeks ago): "Excel misinterprets unquoted
  numeric fields in export as dates for some locales." Workaround: import via
  Data > From Text instead of opening the file directly. 14 tickets closed
  against KI-388 in the last month.
- Last platform release shipped 40 days ago. Reported onset was 6 days ago.
