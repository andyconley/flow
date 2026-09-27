# Adversarial Product Review: step5-cancellation

Reviewer: Product Manager persona. Scope: is this the right slice, at the
right size, now, with honest non-goals and measurable success criteria.

## P1 — Sequencing: this slice is being built on two live runs that never
reached "done," and `v8-live-validation-3` is unblocked and cheap to run first
**Severity: High**

`v8-live-validation-2`'s own follow-up plan (archive.md) says the next steps
are the D6/D7 fix run, then `v8-live-validation-3` "with a new work id." The
fix (`producer-turn-contract`, D6+D7) is already archived and released as
v0.37.1 (CHANGELOG). Nothing blocks running `v8-live-validation-3` today.

Both live runs so far ended in a Flow-caused defect (D4/D5 in run 1's
successor, D7 in run 2), not in a clean completed chartered job. The step 5
design doc explicitly says "real-world validation is deliberately deferred
until step 5 is in place" — but step 5 (cancellation) is itself being
requirements-gathered almost entirely from *symptoms of incomplete live runs*
(the dead work-id trap), not from an actual live-cancel need observed once
the more basic path (a job completing end to end) has been proven. There is
a real risk this slice is solving for the failure mode of an environment that
hasn't yet run a single successful chartered job, and will need to be
revisited once `v8-live-validation-3` finds D8, D9, etc. under different
conditions (e.g., what "abandon" needs to look like once the manager
progress retry or headroom auto-grant machinery interacts with an uncertain
send in a completed-but-partially-uncertain run).

**Disposition:** Run `v8-live-validation-3` first, or at minimum in parallel
on a schedule that doesn't block it. If Andy's actual near-term goal is "get
a live chartered job to complete," that run is one command and a few hours;
this slice is a multi-week engineering effort with an ADR. The two aren't
mutually exclusive, but the requirements doc doesn't argue why cancellation
now beats validation now — it only argues from pain already logged. Ask: if
`v8-live-validation-3` also dead-ends (timeout, crash, another Flow defect),
does this slice's design still hold, or does new evidence reopen R1–R4?
Recommend running validation-3 first and treating this slice's approval as
provisional on its outcome not changing the shape of R1–R4.

## P2 — Scope: three-in-one slice bundles a novel identity/signal subsystem
(R1–R3) with a ledger/status subsystem (R4–R7) with two unrelated CLI
gaps (R8, R9) with a documentation deliverable (R10)
**Severity: High**

The engineer decision (1a) asserts "one slice covers live cancel, stuck
abandon and successor reuse," but the *actual* pain evidenced by the two live
runs is narrower: **abandon + successor** (R4, R5, R6, R7). Both live runs hit
the dead-work-id trap through the `release`-then-stuck path, not through a
need to interrupt a *live* attempt. The requirements doc even admits this:
"the live-run dead end" in the success criteria is entirely about the
abandon path, and live cancel is justified only abstractly ("a live attempt
has no stop path except the 600 s runtime cap").

Live cancel (R1–R3) is the highest-risk, least-precedented part of this
slice: it requires a brand-new control-record file format, a SIGTERM handler
installed in a process that today has zero signal handling, process-identity
verification across pid reuse and host, and two *inferred, unverified*
assumptions flagged in the requirements themselves ("planning must confirm
[SIGTERM interrupts a blocking provider wait] for the Codex, Claude and
Ollama worker paths" and "whether killing the parent's request aborts the
[Ollama] local generation" is "untraced"). If either assumption is false for
even one provider, R2/R3 either don't work for that provider or need a
different mechanism per provider — that's discovered mid-implementation, not
now.

Meanwhile R8 (lead CLI) and R9 (diagnostics additions) are real but
independent gaps: R8 closes `delivery-lead-claim-cli`, which today is
reachable only through Python — a and this is only coupled to cancellation
because abandon happens to reuse `change_lead_claim`'s fencing pattern. It
does not need cancel or the control record to ship.

**Disposition:** Split into two slices:
- **Slice A (do now): abandon a stuck attempt + successor + lead CLI +
  diagnostics for the abandoned/started states.** This is R4–R10 minus the
  cancel-specific parts of R9/R10, and it directly kills the dead-work-id
  trap that both live runs actually hit. It has no unverified assumptions —
  everything in `abandon-seal.md` is `[O]`, not `[I]`.
- **Slice B (defer): live cancel via parent SIGTERM.** This is R1–R3 plus the
  cancel-specific parts of R5 (the `cancelled` receipt status), R9, R10. It
  depends on answering the two open provider-behavior questions, and it adds
  meaningfully more surface (control record format, signal handling,
  identity verification, four extra refusal reasons) for a scenario (a still-
  live attempt Andy wants to kill early) neither live run has actually
  produced yet — the pain evidenced is the 600 s cap being too long, not an
  inability to cancel per se.

If the engineer insists on one slice for architectural reasons (e.g. one
receipt shape for both `cancelled` and `abandoned`, per option B's rationale
in `abandon-seal.md`), at minimum sequence abandon's tests and merge first
so a broken cancel design doesn't block shipping the trap fix.

## P3 — Success criteria are directionally right but not independently
measurable, and the primary metric ("no orphaned process") has no defined
detection method
**Severity: Medium**

- "No orphaned provider or child process" (success criterion 1, AC1) is
  falsifiable only by an operator manually checking `ps` after the fact, or
  by the hermetic test's own bookkeeping of the process groups it started.
  There is no diagnostic command (R9's `inspect-delivery` extension shows
  "which recorded groups are alive," which is good) that answers "are there
  any *unrecorded* stray processes from this attempt" — the requirements'
  own R1 says the control record is "evidence of process identity only," so
  a bug that fails to record a provider group before the parent dies mid-way
  produces exactly the failure this criterion is meant to catch, with no way
  to detect it after the fact. Recommend adding an explicit AC: killing the
  parent between "provider group starts" and "group appended to the control
  record" (the recording race) is tested and its failure mode is defined
  (documented residual risk is fine; silence is not).
- "The dead-end sequence from the live runs no longer kills the work id" is
  good and directly traceable to `abandon-seal.md` section 2's numbered dead
  ends — this is the one criterion tied to real evidence with a clear
  before/after. Keep it, and make it AC3 exactly (it already is).
- "No uncertain send is resent or reclassified without evidence, in any
  path" restates an existing invariant (ADR 0012/0016) rather than
  describing new value; it belongs in the constraints/non-regression section,
  not success criteria, where it dilutes the two real new-capability claims.

**Disposition:** Keep criterion 2 as the headline success metric. Rewrite
criterion 1 to name the detection method (test harness process-group
accounting) rather than an unfalsifiable "no orphaned process." Move
criterion 3 to constraints.

## P4 — Non-goals are mostly honest, but one is a scope-control illusion:
"changing the 600 s runtime-cap path... still records an interruption"
**Severity: Medium**

This non-goal preserves the exact stuck state (`interrupted`, attempt stays
`started`) that R4 (abandon) is built to clean up — the requirements
document even cross-references this ("the 600 s cap path already
demonstrates the target shape... but it never seals a receipt as
`cancelled`" — `live-child-cancel.md` implications section). So after this
slice ships, an attempt that times out at 600 s is *still* stuck exactly
like today, and the operator's remedy is: wait for it to time out, then run
`abandon-delivery` (since no live process holds it once the cap fires and
the parent exits). That's fine as a design choice, but the non-goal reads as
"we're not touching the timeout path" when the real story is "abandon-delivery
is the fix for the timeout path too, we're just not proactively firing it."
This should be stated as a positive claim, not a non-goal, because it's
likely the single most common real-world trigger for the whole slice (every
run so far has been well under 600 s manually interrupted or dead-ended by
`release`, not automatically timed out — so this is untested territory for
AC3's actual applicability).

**Disposition:** Reword this non-goal into an explicit statement in "Desired
outcome" or success criteria: "An attempt that hits the 600 s runtime cap and
is left `started` can be abandoned the same way as any other stuck attempt."
Add an AC that abandon works on a cap-timed-out attempt specifically (not
just the hand-constructed "released, unknown send" fixture in AC3), since
that is the more probable real trigger.

Other non-goals reviewed and judged honest and correctly scoped:
- Protocols 5–7, MCP ingress, charter-sealed auto-cancel, cross-host cancel,
  non-POSIX: all correctly deferred, none quietly needed by the core value.
- "Authenticating actors... telling the Shaper apart from the operator": well
  supported by `shaper-authority.md`'s finding that no such distinction
  exists anywhere else in the codebase today. Consistent, not a shortcut.
- "A graceful checkpoint-then-stop cancel": reasonable to defer, but note
  this means R2's `cancelled` receipt marks in-flight work `unknown` even
  when the child was about to write a durable response — Andy loses that
  spend on every cancel, always, even ones issued a second before natural
  completion. Not a blocker, but should be said out loud as a real cost of
  cancel (worth one line in the ADR under consequences).

## P5 — Missing "2am" affordance: no single command that answers "is
anything stuck right now, and what do I run"
**Severity: Medium**

R9 extends `inspect-delivery` per-attempt, which requires already knowing the
work id and attempt id. At 2am after a run apparently hung, Andy's actual
first question is "which work id, if any, is stuck, and what's the one
command to fix it" — not "given this specific attempt id, show me its
diagnostics." Nothing in R1–R10 provides a run-wide or fleet-wide "what's
stuck" scan. `inspect-delivery`'s R9 addition ("the next action") is good
but only fires once you've already found the right attempt.

This matters more than it looks: the requirements note the recovery_lock
liveness check is *not reliable after a hard parent crash* (`live-child-cancel.md`,
section 2) — meaning a hard crash can look "not live" while a provider
subprocess is still actually running, and `abandon-delivery`'s own reaping
logic (Ca) is the intended answer, but only if Andy knows to run it on the
right work id.

**Disposition:** Add a low-cost AC to R9/R10: a way to list all attempts
across the run (or all runs) currently `started` with no live holder, e.g.
`flow run inspect-delivery --stuck` or equivalent, so the "what do I run"
step doesn't require Andy to already remember which work id hung. This is
small relative to the rest of the slice and is the single highest-leverage
addition for the actual 2am scenario. If cut for scope, it should be an
explicit deferred item with a named follow-up, not silently absent.

## P6 — `--actor` free-text with no Shaper/operator distinction is correctly
scoped, but the ADR should say why cancel authority not being checkable is
acceptable for a *destructive* action, not just an informational one
**Severity: Low**

`decide-expansion` and `change_lead_claim` already use unauthenticated
free-text `--actor`, so reusing that pattern for cancel/abandon is
consistent (P confirmed by `shaper-authority.md`). But those two precedents
are *approve/allocate* actions; cancel/abandon are *destructive and
irreversible* (kill live processes, seal a terminal receipt, end a work
id's normal path permanently). Since Andy is the only operator and there is
no real "who" ambiguity in practice, this is low severity — but ADR 0019
should say explicitly that irreversibility was considered and accepted
given the single-operator context, rather than silently inheriting the
approve-flow's authority model as if the risk profile were the same.

**Disposition:** Add one paragraph to ADR 0019 acknowledging the
approve-vs-destroy distinction and why free-text attribution remains
sufficient here.

## Summary of dispositions

| # | Item | Severity | Disposition |
|---|---|---|---|
| P1 | Sequencing vs `v8-live-validation-3` | High | Run validation-3 first or in parallel; treat this slice's shape as provisional on its outcome |
| P2 | Scope too broad, bundles unverified cancel mechanics with proven abandon mechanics | High | Split into Slice A (abandon+successor+lead CLI+diagnostics, ship now) and Slice B (live cancel, defer pending provider-signal verification) |
| P3 | Success criteria not independently measurable | Medium | Name the detection method for "no orphaned process"; move the resend invariant to constraints |
| P4 | 600s-cap non-goal hides that it's the real trigger | Medium | Reword as positive claim; add an AC for cap-timeout abandon specifically |
| P5 | No "what's stuck" scan for 2am use | Medium | Add a stuck-attempt listing command or explicitly defer it by name |
| P6 | Destructive-action authority model unexamined | Low | One paragraph in ADR 0019 on the approve-vs-destroy distinction |
