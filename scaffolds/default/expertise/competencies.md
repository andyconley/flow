# Flow competency vocabulary

The controlled vocabulary that expertise entries teach. Serialized as a
schema.org `DefinedTermSet` at `flow:competencies`; each term below becomes a
`DefinedTerm` referenced from an entry's `teaches`.

Authored as its own artifact rather than derived from entries. That direction
matters: a source serving three roles must produce three entries with different
required behavior, and a shared competency is what makes that difference
visible instead of accidental. Deriving terms per entry would recreate the
leakage the vocabulary exists to catch.

Terms are role-agnostic. A term names a durable capability; a role holds it; an
entry teaches it against a particular source. The same term appearing under two
roles is expected and is not duplication — the entries teaching it differ.

`competencyRequired` is deliberately unused throughout. It denotes a
prerequisite for understanding a resource, not a condition of its
applicability, and using it as a trigger would misstate the model.

## Terms

### Separate observation, interpretation, assumption, and decision

Keep the four evidentiary states distinct in any artifact another role will act
on, so a downstream reader can tell what was seen from what was concluded.

- Roles: business-analyst, support-lead
- Taught by: "Mark the evidentiary status of every statement"; "Carry
  hypothesis and fact separately across a handoff"

### Ask non-leading questions

Elicit an account without supplying its content, so the answer carries
information rather than agreement.

- Roles: business-analyst, support-lead
- Taught by: "Elicit past behavior, not stated intent"; "Ask for the last
  occurrence, not a description"

### State the evidence that would change the conclusion

Name what would refute or settle a claim at the time the claim is made, so the
claim stays falsifiable after it is handed on.

- Roles: business-analyst
- Taught by: "Leave a requirement undefined while the evidence is thin"

### Preserve competing hypotheses until evidence rules them out

Hold more than one live explanation, and retire each by observation rather than
by plausibility or fatigue.

- Roles: sre, support-lead
- Taught by: "Hold competing hypotheses during a live incident";
  "Evidence-led triage"

### Distinguish contributing conditions from a named cause

Account for failure as conditions that had to coincide, and treat the selection
of any one as a decision about where to stop looking.

- Roles: sre
- Taught by: "Contributing conditions instead of a root cause"

### Account for hindsight when judging past decisions

Reconstruct what was available at the moment of action, and read retroactive
obviousness as a fact about the signals rather than about the person.

- Roles: sre, support-lead
- Taught by: "Reconstruct what was known at the time"; "Do not read the user's
  actions as obvious errors"

### Make applicability conditions explicit alongside a recommended pattern

State where a pattern stops working and what it introduces, so the
recommendation cannot travel without its limits.

- Roles: sre
- Taught by: "State what a mitigation newly makes possible"

### Restate a solution-shaped request as the outcome behind it

Recover the outcome a request is pursuing when the request has already named an
artifact, and carry both forward rather than substituting one for the other.

- Roles: business-analyst
- Taught by: "Reframe a product request as the job behind it"

### Surface dissent by treating failure as already accomplished

Elicit concrete failure accounts by positing the failure as done, which
retrieves scenarios abstract risk questions miss and makes objecting the
assigned task.

- Roles: business-analyst, sre
- Taught by: "Premortem the definition before it is approved"; "Premortem a
  change before it rolls"

### Direct corrective action at conditions rather than at individuals

Aim every remedy at a tool, signal, default, procedure, or constraint, because
a remedy aimed at future attentiveness changes nothing and suppresses reporting.

- Roles: sre
- Taught by: "Postmortem output is a change to conditions"

### Test a familiar pattern match before acting on it

Name the prior case being matched against and take the observation that would
separate this one from it, before the match drives action.

- Roles: support-lead
- Taught by: "Discount the failure mode you saw most recently"

## Coverage

Eleven terms across the sixteen pilot entries. Five terms are held by more than
one role, which is the mechanism working as intended rather than a sign of
overlap to remove.

| Role | Entries | Terms held |
|---|---|---|
| business-analyst | 5 | 5 |
| sre | 6 | 6 |
| support-lead | 5 | 5 |

Every pilot entry maps to exactly one term, and every term is taught by at
least one entry. Roles outside the pilot hold no terms yet; an empty set is a
clean outcome, not a gap to fill by analogy.

## Open

The `teaches` reference is recorded here, entry-side rather than in the agent
files. Completing the join in both directions means adding a `Teaches:` line to
each entry, which is mechanical but changes the authored entry shape and is
better done once the storage format is settled.
