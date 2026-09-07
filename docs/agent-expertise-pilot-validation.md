# Agent expertise pilot validation

A single two-arm comparison on one constructed support ticket. This record
supports a `/flow-define` decision on whether to continue the expertise
capability. It is not an acceptance test of the pattern, and it makes no claim
about behavior on tickets other than the one run.

The question it addresses is the one left open in
`agent-expertise-provenance-handoff.md` and restated in the discovery handoff:
whether an expertise addition changes an agent's output or only lengthens its
prompt.

## Method

Both arms received the same ticket and the same role definition, delivered the
same way — as a prompt to a general-purpose agent, so the delivery mechanism
was identical and the definition text was the only variable.

| Arm | Definition | Lines |
| --- | --- | --- |
| Control | `scaffolds/default/agents/support-lead.md` at `main` (d232925) | 112 |
| Treatment | same file at `f9993e0` | 194 |

The treatment definition is the control plus the 82-line `## Expertise`
section. Nothing was removed; `diff` shows additions only.

The ticket (`docs/evidence/agent-expertise-pilot/ticket-sup-4471.md`) was
constructed to trip the five support-lead entries: a known issue with 14 recent
closures as an availability trap, an unsupported customer causal attribution, a
customer-side configuration change inviting a user-error dismissal, a report
phrased as a conclusion, and no sample file.

The rubric (`docs/evidence/agent-expertise-pilot/rubric.md`) was written and
saved before either arm ran. Scoring was performed against it afterward.

## Result

| Behavior | Control | Treatment |
| --- | --- | --- |
| B1 Evidence-led triage | Partial | Full |
| B2 Handoff integrity | Partial | Full |
| B3 Last-occurrence elicitation | Absent | Full |
| B4 Not user error | Partial | Full |
| B5 Pattern-match discipline | Partial | Full |
| N1 Workaround without distinguishing test | Tripped | Clean |
| N2 Update accepted as cause | Clean | Clean |
| N3 Regional change treated as cause or user error | Clean | Clean |

N2 did not discriminate. Both arms rejected the customer's "started after your
last update" attribution on timeline evidence.

## The independent signal

The control asked the customer to "confirm how they open the files —
double-click versus Data > From Text." The treatment prohibited that question
by name: "do not ask 'were you opening it directly in Excel?', which hands them
the answer we are trying to test."

One arm committed the error the other named in advance. This collision was not
anticipated by the rubric and is the strongest single piece of evidence in the
run, because it cannot be an artifact of how the scoring was framed.

## The diagnostic difference

The control asserted early that "the data in the file is almost certainly
intact" and never carried a genuine regression in the recent release as a live
possibility. The treatment held it as hypothesis 3 and marked it as "the one
that gets buried if we close on the match."

On this ticket, the control's path closes a possible regression as a known
issue during an at-risk renewal window. That is a substantive outcome
difference, not a difference in presentation.

## Cost

The treatment response ran roughly 20 percent longer than the control. The
added length is structural — a facts-versus-hypotheses register and an
evidentiary escalation packet — rather than expanded prose. Both arms produced
a usable triage; the control is competent work.

## Limits

- One ticket, one run per arm. No variance estimate. A second run of either arm
  could score differently.
- The ticket was constructed to trip these specific entries. This establishes
  that the entries fire when their triggers are present. It does not establish
  behavior on tickets where the triggers are absent.
- The entries, the ticket, and the rubric share an author. Pre-registration
  constrains the scoring; it does not make the scorer independent.
- Delivery was via prompt to a general-purpose agent rather than through a
  Flow subagent dispatch. The dispatch boundary named in the discovery handoff
  remains unverified on both runtimes.
- Not tested: whether the entries induce over-investigation of routine tickets
  where the known-issue workaround is the correct first response, and whether
  the observed behaviors are role-specific or generic diagnostic hygiene that
  any role would produce from the same ticket.

## Reading

The result clears the gate that was blocking spend on serialization. It does
not establish the pattern as proven, and the last two items under Limits are
the cheapest way to move it further.
