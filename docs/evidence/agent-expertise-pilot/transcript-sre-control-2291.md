# Control arm — sre without expertise entries

Role definition: `scaffolds/default/agents/sre.md` at `main` (d232925), 109
lines. Incident: `incident-ops-2291.md`. Delivered as a prompt to a
general-purpose agent pointing at the definition and incident files; both arms
received identical delivery. Verbatim final message follows.

---

## Reliability Review Summary

Severity 4, no SLO, zero real requests during the window, one host affected, and the gap is already closed. The correct outcome is a small, cheap follow-up — not a program of work. Most of this review is stating that plainly.

### Service Expectations

- `metrics-dash` is an internal, VPN-only dashboard for platform engineers. Healthy behavior is "reachable during working hours." There is no SLO and none is warranted — defining one for a tool with zero off-hours demand would create alerting obligations with no user to protect.
- Meaningful degradation for this service is an engineer being unable to load the dashboard while working. That did not happen. The 7h 8m unavailability number is real but carries close to zero user impact, and should not be used as a driver for follow-up sizing.
- The severity policy behaved as designed: it suppressed a 02:14 page for a service that nobody needs at 02:14, and filed a ticket that was picked up at 09:05. Do not change this. Paging on this class of failure would be a regression.

### Observability Gaps

One real gap, and it is not in the dashboard's telemetry:

- **Nothing detects a host that exists outside Terraform / `cert-manager` enrollment.** The inventory diff that identified `metrics-dash` was run manually during the incident. Detection today depends on someone thinking to look. That is the only signal worth adding.
- Certificate expiry itself was detected correctly — the synthetic check fired at the moment of failure. No change needed there. A pre-expiry warning (e.g. 14 days out) would have converted this into a ticket before an outage, and is a reasonable low-cost addition if `cert-manager` does not already emit one for enrolled hosts, but it would not have covered `metrics-dash`, which was never enrolled. Enrollment coverage is the higher-value signal; expiry warning is secondary.

Not a gap: logging, tracing, or correlation IDs on this service. Diagnosis took no time. The 7 hours were arrival latency, not investigation.

### Failure Modes

- **Root cause:** a host was created by hand as explicitly temporary, and the migration into Terraform that the creation ticket committed to never happened. The certificate expiring is the symptom; the unenrolled host is the fault; the unclosed temporary-to-permanent transition is the process failure.
- **Blast radius is confirmed bounded.** The inventory diff showed `metrics-dash` was the only unenrolled host. This is a single miss, not a systemic pattern, and should be treated as one. Resist the reading that one missed enrollment proves the enrollment process is broken.
- **Recurrence mode to watch:** the next vendor evaluation or spike that stands up a host by hand. The failure repeats when a "temporary" host outlives the attention of the person who created it. This is a plausible recurrence, but it is currently a sample size of one.
- Recovery was straightforward: reissue and install, 17 minutes from first human contact. No recovery gap.

### Deployment Safety

Nothing to say here that is proportionate. The remediation is enrolling one host in an existing Terraform module and letting `cert-manager` take over renewal. That is a routine, reversible change with an obvious verification step: confirm the host appears in `cert-manager`, and confirm the certificate renews automatically before the next expiry rather than assuming enrollment implies renewal.

### Operational Recommendations

Two actions. Both small.

1. **Enroll `metrics-dash.internal` in Terraform and `cert-manager`.** This closes the actual gap and the commitment the creation ticket already made. Verify the first automated renewal actually fires rather than treating enrollment as done.
2. **Run the inventory diff on a schedule** — the same check that was run by hand during the incident, made periodic, alerting to a ticket queue rather than a page. This is the one durable improvement: it converts "someone noticed during an incident" into "we find out within a cycle." Weekly or monthly is sufficient for a fleet where the current count of unenrolled hosts is one.

**No runbook is warranted.** Rule 7 asks for one when operator-visible failure behavior changes; nothing about failure behavior is changing here, the diagnosis was immediate, and a runbook for "the cert expired, reissue it" would be documentation nobody reads for an event that automation should now prevent.

**Explicitly not recommended,** because the incident does not support the cost:

- An SLO or error budget for this service.
- Changing the severity policy or adding paging for internal-only tooling.
- A broader audit of infrastructure provisioning practice. The inventory diff already answered that question — one host, now known.
- A policy requiring review of all manually created hosts. The scheduled diff achieves the same detection without adding a process gate to exploratory work.

**One open question worth surfacing rather than answering:** the creation ticket said "to be moved into Terraform before it becomes permanent," and no mechanism existed to notice when that condition was met. Whether temporary infrastructure should carry an expiry or a tracked follow-up is a real question, but it is a team process question with one data point behind it, not a reliability finding I can settle from this incident. Worth raising if a second instance appears; not worth building policy for now.
