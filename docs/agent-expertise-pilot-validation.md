# Agent expertise pilot validation

Two-arm comparisons on two constructed support tickets. This record supports a
`/flow-define` decision on whether to continue the expertise capability. It is
not an acceptance test of the pattern, and it makes no claim about behavior on
tickets other than the two run.

The question it addresses is the one left open in
`agent-expertise-provenance-handoff.md` and restated in the discovery handoff:
whether an expertise addition changes an agent's output or only lengthens its
prompt.

The first ticket (SUP-4471) tests whether the entries fire when their triggers
are present. The second (SUP-4602) tests whether they fire when they should
not. The Limits and Reading sections at the end cover both.

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

## Result: the constructed trap (SUP-4471)

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

## Counter-test: a routine ticket (SUP-4602)

The first ticket asked whether the entries fire when their triggers are
present. A second ticket asked the opposite: whether they fire when they should
not. Same two definitions, same delivery, rubric again written before either
arm ran (`rubric-sup-4602.md`).

`ticket-sup-4602.md` is a routine instance of KI-388 where the workaround is
the correct answer. The observation the entries demand — raw file contents
versus rendered contents — is already recorded in the ticket by tier 1 and
reproduced internally. The release is 34 days clear of the reported onset, the
locale is stated, the sample file is attached, and onset coincides with the
customer's own new laptop and fresh Excel install.

| Behavior | Control | Treatment |
| --- | --- | --- |
| P1 Answers | Full | Partial |
| P2 Cites the discriminator | Full | Full |
| P3 Proportionate | Partial | Absent |
| P4 Routes without blocking | Full | Full |
| O1 Re-requests supplied evidence | Tripped | Tripped |
| O2 Withholds the workaround | Clean | Tripped |
| O3 Keeps closed hypotheses alive | Clean | Tripped |
| O4 Escalates as a precondition | Clean | Tripped |
| O5 Length without added action | Clean | Tripped |

Both arms gave the workaround with the correct click path, and both refused to
blame the customer's locale setting. Both re-stated the raw-file read as a
diagnostic step despite tier 1 having done it, though the treatment annotated
it as already done and the control did not.

The arms diverge on what happens next. The control resolved the onset with a
mechanism — a fresh Excel install loses the previous machine's saved import
preferences, so the same file now opens through the default path — and closed:
"Do not escalate this ticket." The treatment held the same facts open as a
second hypothesis, instructed the agent not to close against KI-388 until the
customer compares locale and CSV import defaults across two machines, and
routed the ticket to engineering as a timeline anomaly.

On this ticket the control is the better answer. The treatment converts an
explained onset into homework for a single self-serve user and adds an
engineering touch to a ticket that did not need one.

### What this identifies

The entries carry a trigger for opening a hypothesis and none for closing one.
"Preserve competing hypotheses until evidence rules them out" and "state the
observation that would distinguish this report from the prior case" both fire
on the presence of a known-issue match. Neither has a counterpart that fires
when the distinguishing observation has already been taken and recorded — which
is exactly the state this ticket was in.

The failure is in the entry set, not in the pattern. The competency vocabulary
already names the missing term implicitly: `flow:competencies` has "State the
evidence that would change the conclusion" with no dual for recognizing that
the evidence is in. A sixth support-lead entry on sufficiency — act when the
discriminating observation exists, and say what would reopen it — is the
candidate repair. It is not authored, and this record does not test it.

Note also that severity is doing work here that no entry references. SUP-4471
was an at-risk enterprise renewal where over-investigation was cheap relative
to closing a regression; SUP-4602 is one self-serve seat where it is not. None
of the five entries conditions on stakes.

## Repair: the sufficiency entry (treatment v2)

The gap the counter-test identified was closed with a sixth support-lead entry,
"Act when the distinguishing observation is already in hand", and a matching
term in `flow:competencies`. Both tickets were re-run against the amended
definition, delivery unchanged.

The entry is sourced from the passage in Croskerry the first five drew on but
never used — the dual-process claim rather than the bias catalog. The paper's
own position is that the remedy is not to think harder everywhere but to
recognize the conditions under which fast pattern matching is unreliable and
switch modes deliberately. Its required behavior adds the two things the
counter-test showed missing: cite the already-taken observation and act on it
while naming the signal that would reopen the case, and weigh remaining
investigation against the stakes of the report.

| | v1 | v2 |
| --- | --- | --- |
| SUP-4602 P1 Answers | Partial | Full |
| SUP-4602 P3 Proportionate | Absent | Full |
| SUP-4602 O1 Re-requests supplied evidence | Tripped | Clean |
| SUP-4602 O2 Withholds the workaround | Tripped | Clean |
| SUP-4602 O3 Keeps closed hypotheses alive | Tripped | Clean |
| SUP-4602 O4 Escalates as a precondition | Tripped | Clean |
| SUP-4602 O5 Length without added action | Tripped | Clean |
| SUP-4471 B1-B5 | Full | Full |
| SUP-4471 N1-N3 | Clean | Clean |

On SUP-4602 v2 marks steps 1 and 2 "Already done", asks the reporter for
nothing, states the reopening signal explicitly, and closes: "No engineering
escalation on SUP-4602. Resolve with the workaround." It gives the stakes
reason in the same line — a single self-serve seat with no renewal event "does
not warrant carrying an open question further." It keeps the affordance finding
that both earlier arms produced, routed to product without blocking the reply.

On SUP-4471 nothing regressed, which was the risk worth testing. v2 still
refuses the match, and states why in the entry's own terms: KI-388 "is a match,
not a confirmation; the distinguishing observation has not been taken."

The stakes clause also improved the trap ticket, which was not anticipated.
v1 gathered evidence and escalated after it. v2 sends the workaround
immediately as an explicit interim measure to protect the month-end deadline,
has support produce a known-good re-export so the customer can stop re-keying,
and escalates in parallel with evidence-gathering rather than after it —
reasoning from the renewal risk and the hard date. Weighing investigation
against stakes cuts both ways: it withdraws effort from the single seat and
front-loads relief on the at-risk account.

## Limits

- Two tickets, one run per arm on each. No variance estimate. A second run of
  any arm could score differently.
- Each ticket was constructed to probe a specific direction — the first that
  the entries fire on their triggers, the second that they fire when they
  should not. Neither samples the real ticket distribution.
- The entries, both tickets, and both rubrics share an author. Pre-registration
  constrains the scoring; it does not make the scorer independent.
- Delivery was via prompt to a general-purpose agent rather than through a
  Flow subagent dispatch. The dispatch boundary named in the discovery handoff
  remains unverified on both runtimes.
- Still not tested: whether the observed behaviors are role-specific or generic
  diagnostic hygiene that any role would produce from the same ticket.
- The sufficiency entry was authored against a failure the counter-test
  produced, and tested on the ticket that produced it. That is a repair
  confirmed on its own case, not a generalization. A ticket neither ticket
  resembles has not been tried.

## Reading

The pattern changes agent output, in both directions. On a ticket where the
known-issue match is a trap it produces a materially better answer; on a ticket
where the match is correct it produces a worse one, by keeping a settled
question open and spending a customer's time and an engineering touch on it.

That is enough to justify spending on serialization. The gap the counter-test
identified — no sufficiency trigger, no conditioning on stakes — was an
authoring gap, and the six-entry set no longer shows it on either ticket.

The more useful finding is about method rather than about these entries. A
one-directional test would have shipped the five-entry set, because on the
ticket it was written for the set performs well. The failure was only visible
from the opposite direction, and the repair for it improved both cases. Entry
sets should be authored and tested in pairs of opposing tickets, and the
counter-ticket belongs in the corpus alongside the entry it constrains.
