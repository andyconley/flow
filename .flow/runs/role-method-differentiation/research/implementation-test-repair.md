# Test design: two-role method repair

## Verdict

The prior records are useful failed history, not rerunnable proof. They retain
successful response envelopes and outputs, but not the prompt text, command,
injected role body, effort, output cap, or standalone parity manifest. In
particular, the old product control already identifies a cliff and flat value,
and the old quality control already files the critical; neither can establish
the approved no-tie gate. Keep them intact and mark them superseded.

The repair needs two independent layers of proof:

1. deterministic tests that prove the shipped contract and both generated
   adapters contain it; and
2. a frozen, criterion-level behavioral comparison that proves a treatment
   advantage without treating verbosity as a win.

## Deterministic contract tests

Extend `ShippedCorpusTests` with literal expectations rather than broad
keyword searches. The role-body test currently has obsolete expectations for
unselected methods (`failure or kill condition`, `derive the required
contents`, and `observed, read, or author-asserted`), so it would pass the
wrong repair.

### Product-manager oracle

Representative input: the shipped `product-manager.md` and its corpus.

Expected observable result:

- the role body contains the complete executable instruction to estimate cost
  for one unit of delay, divide by delivery duration, and sequence by the
  result rather than importance;
- its corpus contains exactly the selected replacement entry id and one
  `teaches` edge for the replacement competency;
- it contains neither the superseded `tie-priority-to-an-outcome-and-evidence`
  entry nor the matching competency/reverse-join text;
- the entry has a non-empty Reinertsen source, edition/date when the selected
  citation supplies one, and a non-empty locator; and
- the common `sync.agent_body` rendering path includes the replacement entry
  once.

The implementation should freeze the exact replacement id and competency name
as constants in the test. The expected id should be the eventual literal
`flow:entry/product-manager/...`, rather than an assertion that merely finds
an entry whose prose mentions "decay". That prevents a second, redundant
entry from silently satisfying the test.

### Quality-reviewer oracle

Representative input: the shipped `quality-reviewer.md` and its corpus.

Expected observable result:

- the role body contains the complete instruction: before a Critical, state a
  plausible correct explanation, cite the specific evidence that rules it out,
  and otherwise ask a question or lower severity;
- its corpus contains exactly the selected alternative-explanation replacement
  entry and its single competency edge;
- it contains neither the superseded observable-proof entry nor the rejected
  omission/evidence-strength entry, including their reverse competency joins;
- the entry carries a non-empty Heuer source and the literal `Chapter 8`
  locator; and
- the common `sync.agent_body` rendering path includes the replacement once.

Again, assert exact ids/names selected by the implementation. A test that only
looks for `Critical` or `evidence` is vacuous because the pre-repair role body
already contains both concepts.

### Join and render oracle

Use existing corpus loading and `sync.agent_body`, which is the shared Claude
and Codex source path. For both changed roles, assert all of the following in
one focused test per role:

- corpus entry-id set equals the expected entry-id set for that role (not a
  subset);
- `teaches` has exactly one expected `{id, name}` edge for the replacement;
- `expertise.reverse_join_problems(SCAFFOLD, COMPOSED_ROLES)` is empty;
- the rendered body has one `## Expertise` heading and exactly one matching
  entry heading.

This is the lowest test level that proves the composition contract. The user
adapter sync checks remain delivery validation; they do not replace this
isolated renderer assertion.

## Meaningful mutation check

Mutate the product-manager role body by removing the sentence containing both
`cost for one unit of delay` and `divide it by delivery duration`. Run the
named executable-boundary test and require it to fail because that exact
contract is absent. Restore the exact original sentence, verify the named test
passes, then run the focused suite.

This is meaningful because the body instruction is the behavioral surface
being added. Deleting an unrelated heading, a corpus field already rejected by
the loader, or only the word `decay` would not prove that the contract test
catches loss of the selected method. Record the failing command, non-zero exit
status, assertion name, restore diff, and passing rerun in validation results.

## Frozen behavioral envelope

Create a new versioned envelope, for example
`docs/evidence/role-method-differentiation/repair-2/manifest.json`, before
dispatch. It is the sole source of truth for every arm. Store raw request and
response records separately and reference them by relative path and SHA-256.

### Required parity fields

The manifest must record these exact fields for every role/case/arm:

| Field | Requirement |
| --- | --- |
| role, case, arm | `product-manager` or `quality-reviewer`; `primary` or `counter`; `treatment` or `control` |
| prompt | complete bytes, SHA-256, and an identical hash for treatment/control of the same role and case |
| provider/client | provider name, client version, executable path, and full replay command with no credential values |
| model settings | model id, effort/thinking setting, temperature if supported, max turns, output cap/token budget, tool/web-search policy, and fast-mode setting |
| body source | body file path, composition inputs, body SHA-256, and injection mechanism |
| control provenance | `HEAD` revision, `git show <revision>:<role-body-path>` command, and SHA-256 of its exact emitted body |
| treatment provenance | current repository revision, dirty-tree SHA-256, composed/current body SHA-256, and the corpus/role-body paths contributing to it |
| execution outcome | start/end time, exit status, session id if available, `is_error`, terminal reason, turn count, and raw response SHA-256/path |
| scoring | frozen criterion ids, scorer identity, evidence offsets or short excerpts, per-arm boolean result, and gate result |

Treatment/control body hashes must differ only because their role bodies differ.
Prompt, provider, model settings, output limit, tools, and invocation method
must match inside each pair. A difference is a failed parity check, not a note.
The fixed pre-change control can use the current known source revision only if
the manifest records it explicitly; for reference, the present `HEAD` body
hashes were product manager `db45fab8ca7a50d78d25f149f560f4076bc86002ce5627960da274c71dd3d54b`
and quality reviewer `4cd2d84d7500bc240bafb5c79f7f3cf8cff738195b870aad5ed4acbe0eea3592`.

## Frozen behavioral cases and scoring

The scorecard should use booleans, not an aggregate quality score. An output
may be fluent and still fail a method predicate.

### Product-manager primary

Use three explicit options with fixed data: one cliff (with date and loss),
one gradual weekly loss, and one flat value, each with a stated delivery
duration. Ask for an ordered sequence and calculations. The fixture must make
the cost-of-delay/divided-by-duration ordering differ from an importance-only
ordering, so merely naming a deadline cannot pass.

| Criterion | Treatment pass predicate | Control predicate required for role gate |
| --- | --- | --- |
| PM-P1 shape | Names the supplied shape for each option: cliff, gradual, and flat. | false |
| PM-P2 calculation | Computes or explicitly compares each supplied delay-cost/delivery-duration value using the fixture data. | false |
| PM-P3 sequence | Orders the work according to that comparison and explains a differing importance-only order would be wrong. | false |

Primary treatment passes only if PM-P1 through PM-P3 are true. The control
must be false on **each** item. If control satisfies any item, if either arm
errors, or if a scorer cannot locate evidence for an item, product-manager
fails. Do not rerun selectively after seeing an output; a new fixture requires
a new frozen manifest and starts a new comparison.

### Product-manager counter

Use options explicitly stated to have flat value over the decision horizon,
with no external date, decay, or loss-per-delay evidence. Treatment passes only
when it says the time-sensitive method does not distinguish the options and
does not invent a deadline, decay curve, or urgency. It may identify a needed
tie-breaker, but must not present an unsupported one as fact. A treatment
failure here fails the role even if primary passes.

### Quality-reviewer primary

Supply a concrete review packet: a claimed Critical, a plausible correct
explanation, and a specific acceptance criterion or observed code/test result
that contradicts that explanation. The contradiction must be textual and
unambiguous; for example, a proposed benign database validation is ruled out
by an approved requirement that rejection occur before persistence plus an
observed path that persists first. Ask for a review finding.

| Criterion | Treatment pass predicate | Control predicate required for role gate |
| --- | --- | --- |
| QR-P1 alternative | States the supplied plausible explanation under which the artifact would be correct. | false |
| QR-P2 ruling evidence | Cites the exact supplied requirement, code path, or observed result that rules that explanation out. | false |
| QR-P3 calibrated Critical | Files a Critical only after QR-P1 and QR-P2, and connects its severity to the ruled-out explanation. | false |

Primary treatment passes only if all three are true and the control is false on
all three. A control Critical by itself does not demonstrate a treatment
advantage; it must still miss the prerequisite explanation/evidence criteria.
If the control independently supplies every criterion, record the tie and fail
the gate rather than changing the rubric after scoring.

### Quality-reviewer counter

Use the same apparent serious issue but remove the discriminating requirement
or observed result, leaving the plausible explanation unresolved. Treatment
passes only when it explicitly preserves the explanation as unresolved and
records a question or lower-severity finding. Any Critical about that issue is
an over-application failure. The treatment may request a discriminating test
or requirement clarification; it may not manufacture evidence.

## Criterion-level stopping rule

For each role, calculate the following after all four records are complete:

```text
role_pass =
  parity_passes_for_all_pairs
  AND all_four_records_complete_without_client_error
  AND all_primary_treatment_criteria_true
  AND all_primary_control_criteria_false
  AND treatment_counter_passes
```

There is no majority, average, wording-quality, or rerun exception. Any false
term is that role's failed gate. The combined five-role release remains blocked
until both repaired roles pass and the existing architect, test-engineer, and
lead-developer evidence is cited with its prior scope and status. The old
three-role score stays a failed historical record; it must never be relabeled
as a pass based on this repair.

## Execution sequence

1. Implement exact replacement ids, source locators, role-body wording, and
   reverse joins.
2. Add the deterministic literal-set/absence/render tests and run them.
3. Perform and record the product-body mutation check.
4. Freeze the manifest and fixtures before any live dispatch.
5. Run all eight records without changing a prompt, body, or scoring rule.
6. Score each criterion with response evidence, apply the stopping rule, then
   run delivery validation only if both role gates pass.
