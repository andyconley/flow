# Treatment arm — sre with expertise entries

Role definition: `scaffolds/default/agents/sre.md` at `f9993e0`, 208 lines.
Incident: `incident-ops-2291.md`. Delivery identical to the control.
Verbatim final message follows.

---

## Reliability Review Summary

Scope note: Sev-4 internal dashboard, no SLO, no customer impact, zero real user requests during the window. The proportionate output is a small number of condition changes, not a program of work. The interesting finding here is not the expired certificate.

### Service Expectations
- Healthy behavior for `metrics-dash`: reachable over the VPN with a valid TLS chain during working hours. That is the real expectation; the 7h 8m of overnight unavailability cost nothing and the severity policy that suppressed the page was correct.
- No SLO exists and none is warranted at this criticality. What is missing is not a target but a stated tier: "business-hours best effort, no page outside them" should be written down so the next reviewer does not re-argue whether the suppressed page was a miss.
- The dashboard is a diagnostic tool for other incidents. Its degradation matters mainly when something else is already wrong — worth noting because that is the scenario where a 7-hour outage would not have been free.

### Observability Gaps
- The conditions that had to hold together: (1) a host was created outside the Terraform path, so it never reached `cert-manager`; (2) the creation ticket's "move it before it becomes permanent" had no owner, date, or expiry attached to it; (3) nothing compared the live host inventory against the enrolled set until a human ran that diff by hand during the incident; (4) certificate expiry itself was only visible as a synthetic failure after the fact.
- Defenses that were supposed to catch each: (1) convention that hosts come from Terraform — advisory only, nothing enforces it; (2) the ticket itself — a note, not a control; (3) no defense existed at all; (4) synthetic check — it worked exactly as designed, it just fires at expiry rather than before it.
- The detection gap is the finding, separate from the trigger. The inventory diff that identified the unenrolled host is a query that could have run every day for 16 days and did not. That gap is generic: it would have caught this host, and it will catch the next one, regardless of why that host was created.
- Second gap: no signal exists for "certificate expires in N days" on hosts outside `cert-manager`. Inside `cert-manager` renewal is automatic so the signal is unnecessary; outside it, nothing watches. The blind spot is precisely the population that needs watching.

### Failure Modes
- Unenrolled host drifts to expiry. Mitigation: a scheduled inventory diff (live hosts vs. `cert-manager` enrollment) that files a ticket on any delta. What this newly makes possible: the diff becomes a source of noise during legitimate short-lived hosts — vendor evaluations, spike environments — and a diff that files tickets nobody closes will be muted within a quarter. Mitigate the mitigation by giving the diff an explicit exemption field with a required expiry date, so a temporary host is expected-absent until its date passes rather than silently absent forever.
- Expiry-based alerting on the unenrolled set. What it newly makes possible: an alert that fires at 14 days and then daily is a slow-burn nuisance on a Sev-4 service; a single ticket at 14 days, escalating to a page only if the host is tier-1, keeps it proportional.
- Overnight failure of a diagnostic tool during a concurrent incident. Currently unmitigated and, at this tier, acceptably so — but it should be a named acceptance rather than an oversight. If `metrics-dash` becomes a dependency of incident response, its tier changes and so does the page suppression rule.

### Deployment Safety
- Enrolling `metrics-dash` in Terraform is itself a small cutover: importing a hand-built host into state can diverge from the running configuration. Premortem, briefly — this import rolled out as planned and took the dashboard down: state import rewrote a hand-tuned nginx or Grafana setting; the Terraform module's own cert issuance raced the freshly installed manual certificate; the module applied a hostname or DNS assumption that did not match the manual build.
- Guardrails that follow from those: run `terraform plan` against the imported host and require a human to read the diff before apply, do the apply during working hours, and keep the current certificate and config backed up so revert is a file copy rather than a rebuild. Rollback trigger: any plan diff touching resources outside the certificate and enrollment path.
- The inventory diff job rolls out safely in report-only mode first — run it for a week and read what it finds before letting it file tickets. That also calibrates the exemption list before the noise starts.

### Operational Recommendations
Each item names a condition and the change to it. None of them is a person being more careful.

1. Enroll `metrics-dash.internal` in the Terraform module and `cert-manager`, with the plan-review and working-hours guardrails above. Closes the immediate trigger.
2. Add a scheduled inventory diff — live hosts vs. `cert-manager` enrollment — running daily, report-only for the first week, then filing a ticket on any delta. This is the detection change; it is worth more than item 1 because it does not depend on knowing why a host was missed.
3. Give the host-creation ticket template a required "temporary until" date and owner field, and have the inventory diff treat that date as the exemption expiry. The condition being changed is that "temporary" was a word in prose with nothing reading it; now it is a field with a deadline that a job enforces.
4. Write down the service tier for `metrics-dash` — business-hours best effort, page suppressed outside them — and state the re-tier trigger: if it becomes a required tool during incident response, the suppression rule gets revisited.
5. Not recommended: a runbook for this. Operator-visible failure behavior did not change, the recovery was a 17-minute certificate reissue by the first engineer who saw the ticket, and a document for that would be shelfware. If item 2 produces recurring findings, revisit.

On the timeline: there is no human decision to reconstruct here. Nobody was on duty, nobody saw a signal, and the first engineer to see the ticket fixed it in 17 minutes. The 16-day gap between host creation and expiry likewise contains no decision point — the ticket said "before it becomes permanent," and no instrument anywhere told anyone that the moment had arrived. That is the system's signal gap, not anyone's lapse, and item 3 is the fix for it.
