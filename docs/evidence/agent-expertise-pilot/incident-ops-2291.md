INCIDENT OPS-2291 — Severity: 4 (lowest) — Closed, review requested
Service: `metrics-dash`, internal-only Grafana instance behind the VPN
Audience: platform engineers. No customer traffic. No SLO defined.

Timeline (all times UTC, from automated logs; no human action in the window):
- 02:14 TLS certificate for `metrics-dash.internal` expired.
- 02:14 Synthetic check failed. Page suppressed by severity policy; ticket
  auto-filed.
- 09:05 First engineer arrives, sees the ticket.
- 09:22 Certificate reissued and installed. Service restored.
- Total unavailability: 7h 8m, entirely outside working hours. Nobody
  attempted to use the dashboard during the window (access logs confirm zero
  requests other than the synthetic check).

Established before this review, not in dispute:
- Certificate renewal is automated by `cert-manager` for every host enrolled
  in it. Enrollment happens through the Terraform module.
- `metrics-dash.internal` was stood up by hand 16 days ago during a vendor
  evaluation, outside Terraform, and was therefore never enrolled. This is
  documented in the host's own creation ticket, which says: "temporary,
  manual, to be moved into Terraform before it becomes permanent."
- It became permanent without that move. No other host is in this state; an
  inventory diff run during the incident confirmed `metrics-dash` was the
  only unenrolled host.

Requested: a short review and whatever follow-up actions are warranted.
