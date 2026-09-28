# Adversarial Product Review: step5-operational-handback (revision 1)

Reviewer: `adversarial-product` (product-manager subagent, read-only). The coordinator saved this verbatim from the subagent's hand-back.

## P-F1. The PR is large enough that "one run, one PR" is a real delivery risk, not a formality
**Severity:** Important
**Hits:** E1, R1–R17, AC1–AC23

The slice touches a contract-version bump (R8), a new sealed-field set with runner ceilings, a new tranche-expansion unit reusing (and stress-testing) ADR 0017's one-unit machinery (R8–R12), a new persisted artifact class with its own file-permission and reuse semantics (R2), a rewritten manager observation shape (R1), grant-history events across seven call sites (R3), two new CLI commands with 16 named verification checks each doing full-row comparison (R7, R13–R16), a seal rewrite shared across three call sites (R6/P6), and a full regression pass with zero skips (AC22). That is measurably larger than `step5-cancellation`, the precedent E1 cites, and every review pass will be reading a diff that spans ledger schema, contract validation, CLI, and docs simultaneously.

E1 (one PR) is Andy's fixed decision, so I'm not recommending it be split. But the coordinator's own R-level scoping (not E1–E3 themselves) has room to shrink. The smallest slice that still delivers all of E1–E3 is: R1 (manager identity), R7 (trace), R8–R12 (cap), R13–R16 minus V10 (verify-receipt), R6 (recovery actor — one-line fix, high value, cheap). **Candidate to cut or defer to a fast-follow run:** R2 (manager request text storage) and its dependent V10/AC2/AC10-reuse-edge-case. It closes a real gap (`manager-prompt-text-inspection`) but is the one requirement whose file-lifecycle rules (0600, O_EXCL, digest-bound reuse-on-resend, refuse-on-mismatch-before-any-provider-call) are independent of trace/cap/verify and could ship as its own one-PR run without blocking the rest.
**Recommendation:** Ask Andy explicitly whether R2 should be cut from this PR before implementation starts, given it's the most severable, self-contained piece.

## P-F2. `MAX_LINEAGE_TOKENS` and the default charter values are left as an open question, but the enforcement machinery ships anyway
**Severity:** Important
**Hits:** R8, AC8, "Open questions for planning" item 1

The requirements explicitly punt "the value of `MAX_LINEAGE_TOKENS`, and the default charter values the Shaper proposes" to planning, with no calibration method specified. AC8 only tests that malformed values are refused — it never tests that the shipped defaults are large enough for real work. Flow already has real usage data from `v8-live-validation-2` and `v8-live-validation-3` (the same runs this slice cites as motivation). If the ceiling and defaults are picked without reference to that data, the first live run after this ships is as likely to hammer `decide-expansion` on every other call as it is to catch a runaway lineage — which defeats E2's "automatic... within headroom" and reproduces exactly the escalation-fatigue this slice is supposed to prevent.
**Recommendation:** Require planning to derive `MAX_LINEAGE_TOKENS` and the default `max_lineage_tokens`/`token_tranche`/`unobserved_send_tokens` from the observed per-lineage charged-token totals of `v8-live-validation-2`/`-3` (data already on hand), and record the derivation in ADR 0020, not just the mechanism.

## P-F3. Tranche units (P3) are the right engineering fit but a legibility risk the requirements don't mitigate
**Severity:** Suggestion
**Hits:** P3, R10, R7, AC12

Research (§4, Token cap option B) already flags this: "the units are unintuitive, and headroom has to be expressed in tranches." The requirements confirm the mechanism (tranches reusing ADR 0017's amount=1 machinery) is the right build choice given E2 says "escalates," but nothing in R7 (trace) or R10 (pre-grant check) specifies that operator-facing messages translate tranche counts back into absolute token numbers. Andy auditing a paused attempt at 2am should not have to multiply `tokens_granted × token_tranche` in his head to know how many tokens are actually available.
**Recommendation:** Add an explicit requirement that `trace` totals, the `decide-expansion` pending detail, and refusal reason text always show absolute token counts (granted/available/cap), with tranche counts only as a secondary detail — not the reverse.

## P-F4. P2's sealed `unobserved_send_tokens` charge has no guidance for what value is safe, and the requirements don't ask for one
**Severity:** Suggestion
**Hits:** P2, R9, AC9, AC11

The sealed-charge design is sound and correctly fail-safe in principle (R12 honestly documents the resulting overshoot bound). But the actual number is a judgment call with no stated basis, and if set too low relative to a real timed-out call's true usage, the "at most one call" overshoot bound in R12 quietly becomes "at most one call, of unknown size" in practice — the documentation is honest about the *mechanism* but the requirements don't ask anyone to be honest about whether the *chosen number* is realistic.
**Recommendation:** Same fix as P-F2 — derive the default from the largest observed single-call usage in the existing live-run ledgers, plus a stated safety margin, and record the rationale in ADR 0020.

## P-F5. `verify-receipt`'s `{check, status, detail}` output is specified for detection, not diagnosis
**Severity:** Important
**Hits:** R13, R14, AC16

AC16 requires each of V1–V16 to flip to `fail` on its matching tamper and requires the *other* checks stay clean — good specificity proof. But nothing in R13/R14 requires `detail` on a `fail` to name the mismatching field and both values (expected vs. found). Without that, verify-receipt tells Andy *that* V3 or V9 failed but not *what* differs, and he's back to opening the ledger by hand to find it — which is the exact scripting pain (`runtime-evidence-completion-manifest`) this slice exists to close. Detection alone is not the outcome; the outcome is auditing without a script.
**Recommendation:** Add to R14/AC16 that a `fail` detail names the specific field(s)/row id and both compared values (or a diff), not just "mismatch."

## P-F6. `trace` is specified as a complete-but-flat dump; it has no "why is this stuck" headline
**Severity:** Important
**Hits:** Desired outcome ("Andy... auditing a finished or stuck attempt"), R7, AC7

R7 lists a comprehensive set of per-row fields and per-attempt/per-lineage totals — genuinely closes `delivery-per-call-timings` and beats hand-written scripts for completeness. But the stated audience need is auditing a *stuck* attempt, and nothing in R7 or AC7 requires the tool to lead with the answer to "why is this paused, and on what." Andy would still have to scan the row list to find the one row that's `pending`/paused and reconstruct the blocking reason from its grant history and totals. That's less scripting than today, but it is still manual correlation, just against a nicer table instead of raw ledger rows.
**Recommendation:** Add a requirement that for a non-terminal attempt, `trace` prints a one-line status banner naming the blocking reason (e.g., `token_cap` pause awaiting `decide-expansion`, since <timestamp>, on call <id>) ahead of the per-row detail, and pin it as a golden-output AC the way AC7 pins the JSON schema.

## P-F7. Two recurring live-run pains this slice's own evidence surfaces are not addressed and not named as non-goals
**Severity:** Important
**Hits:** Success criteria ("`receipt_check.py` is redundant"), Non-goals, capability-gaps.jsonl (`job-charter-sealed-digest`, `run-evidence-symlink-hygiene`)

`job-charter-sealed-digest` ("the per-job charter passed as input evidence is not covered by the sealed authority digests; its integrity rests on a hand-recorded hash") and `run-evidence-symlink-hygiene` ("a provider CLI writes an absolute symlink into attempt evidence; nothing strips or rejects it") were each observed twice, across `v8-live-validation`, `-2` and `-3` — the same runs this slice's success criteria and R2/R6 cite as its evidence base. R7 (Authority check) explicitly covers `shaper-contract.json` and `delivery-charter.json` digests but not the per-job charter. Neither gap appears in the Non-goals list. The success criterion "`receipt_check.py` is redundant... only the stub scan and chartered-facts text search remain uncovered" is therefore not quite true against the full set of hand-checks live reviewers actually needed — it's true only for the checks this requirements doc chose to enumerate.
**Recommendation:** Either fold the job-charter digest into V7/R14 (it looks like a small addition to an existing check), or explicitly add both gaps to Non-goals with a one-line reason, so AC23's "redundancy" claim is honest about what still needs a script or a manual symlink scan after this ships.

## P-F8. Manager-request-file reuse-on-recovery-resend logic (R2) is a narrow but real correctness edge with no test for the ambiguous case
**Severity:** Suggestion
**Hits:** R2, AC2

R2/AC2 specify: identical bytes on resend reuse the file; different bytes refuse and leave the file unchanged. That's clear for the binary case. It's not specified what happens when the *same* `call_id` is resent after a `grant_id` rotation but the manager's rendered prompt legitimately changes (e.g., a retried call with updated checkpoint context but the same nominal call) — is that "different bytes, refuse" or is it expected to mint a new file under a new identity? If R2 is kept in-scope (see P-F1), the AC should include this case explicitly rather than leaving it to be discovered as a first-live-run surprise.
**Recommendation:** Add a fixture case: a legitimate recovery resend with genuinely different rendered prompt text, and confirm the refusal (or the intended alternate path) is the one Andy actually wants operationally, not just the one that's easiest to implement.

## P-F9. `flow run trace` has no scoping/filter option for a long lineage
**Severity:** Suggestion
**Hits:** R7, AC7

R7 prints every manager call and action in ledger order for the attempt and its predecessors, with no `--status`, `--since`, or row-count limit. For a lineage with several recoveries and escalations (the fixture lineage itself has an abandoned first attempt, an automatic grant, an escalation, and a D5-style recovery — and that's the *minimal* test case), the practical output could already be long. `--json` helps scripting but doesn't help a human scanning the terminal.
**Recommendation:** Not blocking for this PR, but worth a one-line note in the CLI reference that `--json | jq` is the intended path for large lineages, or add a cheap `--status` filter if it's low-cost to include.

## Verdict

The requirements are unusually rigorous. Three things stand out as exactly the kind of proof this domain needs: the fixture-lineage discipline, the one-tamper-one-failure test design (AC16), and the shared-comparison-function requirement (P6). R1–R6 and R13–R16 map cleanly onto the four named capability gaps:
- `runtime-evidence-completion-manifest`;
- `delivery-per-call-timings`;
- `manager-prompt-text-inspection`;
- `recovery-actor-provenance`.

P1, P4, P6, P7, P8 and P9 are sound and need no rework. P2 and P3 are the right mechanisms. They ship without the calibration data (P-F2, P-F4) or the operator-facing translation (P-F3) that would make them safe and legible on day one.

I would not block definition approval on this review. But I would ask Andy to decide three things explicitly before implementation starts:
1. Whether R2 stays in this PR or moves to a fast-follow (P-F1).
2. Whether the token-cap defaults are derived from existing live-run data before merge, rather than picked arbitrarily (P-F2, P-F4).
3. Whether the output of `trace` and `verify-receipt` gets a diagnosis-first requirement (P-F5, P-F6), so the tools genuinely retire the hand-written scripts instead of producing a nicer thing to read by hand.

P-F7 (job-charter digest, symlink hygiene) should at minimum be named as an explicit non-goal, so the success criteria's claim that `receipt_check.py` is redundant stays honest.
