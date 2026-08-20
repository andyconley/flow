# Incident Management Standard

This standard defines how teams respond to, learn from, and reduce operational incidents.

## Command structure

Incidents should have clear roles, such as:

- incident commander
- communications lead
- subject matter experts
- scribe

One person must own the incident.

In small teams, one person may wear multiple roles, but responsibility should still be explicit.

## Severity model

Projects should define severity levels with:

- customer impact definition
- response expectations
- notification expectations

## Runbook rule

Every meaningful alert should have a runbook.

A runbook should include:

- symptom
- diagnosis steps
- remediation steps
- escalation path
- post-incident follow-up expectations
- whether the symptom can also be normal, and the check that tells the two apart

`templates/runbook.md` carries this structure.

Alerts without runbooks are guesses. Runbooks without ownership decay quickly.

## Post-incident learning

Post-mortems should be blameless and should produce owned, tracked actions rather than vague lessons.

## Game days

Critical systems should practice failure scenarios before production incidents force the first rehearsal.

## Incident metrics

Useful operational measures include:

- time to detect
- time to mitigate
- time to recover
- repeat incident rate
- alert noise and on-call toil

## Relevant standards and references

Principles:

- blameless post-mortems
- clear incident command
- runbook-driven response

Useful references:

- SRE incident management practices
- severity models
- game-day exercises
