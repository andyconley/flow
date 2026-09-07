TICKET SUP-4471 — Priority: High — Assigned: Support Lead
Reporter: Dana Whitfield, Ops Manager, Meridian Freight
Account: Enterprise, renewal in 6 weeks, flagged at-risk by CSM

Subject: CSV export is corrupting our shipment data

> Your CSV export is corrupting our data. We've had three bad files this
> month. Numbers come through wrong — we've seen shipment weights show up as
> dates. It started after your last update. My team has gone back to
> re-keying everything by hand and it's costing us hours a day. We need this
> fixed before month-end close on the 30th.
>
> I should mention someone on my team changed the regional format setting a
> few weeks back, but that shouldn't matter.

Internal notes:
- Known issue KI-388 (opened 3 weeks ago): "Excel misinterprets unquoted
  numeric fields in export as dates for some locales." Workaround: import via
  Data > From Text instead of opening the file directly. 14 tickets closed
  against KI-388 in the last month.
- No sample file attached.
- Last platform release shipped 11 days ago.
