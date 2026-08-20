# Runbook: <system or tool>

Use this template for symptom-first operational documentation: one section per
symptom an operator can actually observe, in the operator's words.

- Subject:
- Scope (versions, environments):
- Owner role:
- Reviewed:

## <Observable symptom, in the operator's words>

- Normal case: [when this symptom is the system working as designed. Fill this
  in even when it is "never" — a symptom with no benign explanation is worth
  saying out loud.]
- Confirm it's a fault: [the one concrete check that separates normal from
  broken — a log line, a query result, a state or config value, a threshold]
- Diagnosis steps (if fault):
  - [step]
  - [step]
- Remediation (if fault): [operator-safe fix steps, or the reason there is none]
- Escalate to: [role or rota, not a person's name]
- Escalate when: [concrete signals — unable to diagnose past step N, data loss
  plausible, customer-visible, requires a code change]

## <Next observable symptom>

[Same structure.]

## Post-incident follow-up

- [Item to track: monitoring, documentation, hardening, or backlog entry.]
