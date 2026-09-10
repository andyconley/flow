# Acceptance proof audit: test engineer

## Scope and method

I read the approved requirements, acceptance criteria, plan, validation plan,
implementation handoff, the complete `tests/test_expertise_composition.py`
module, frozen manifest and scorecards, all four prompts, all four frozen role
bodies, all eight raw Claude result envelopes, execution metadata, scores,
mutation record, retained lead-developer inventory, and delivery logs.

I independently recomputed the repair-2 manifest digest
`8b8b8138c84cf111aa07942ad88fc68db16566f92aac38c230fdf9e384d2ed01`,
all eight raw-response hashes, all four current treatment-source hashes, and
the two frozen control-body hashes from the stated `git show` revision. They
all match their recorded values. The current lead-developer hashes also match
the retained inventory. I reran the focused composition suite: 45 tests pass.

## Proof assessment

| Acceptance area | Evidence | Result |
| --- | --- | --- |
| Product replacement, provenance, removal, joins, and rendering | Corpus/role assertions, reverse join tests, shared renderer test, and final focused suite | Pass |
| Product behavioral advantage | Frozen primary and counter records, criterion scorecard, and strict gate | **Fail**: treatment misses `PM-P2`; control satisfies `PM-P1` and `PM-P3` |
| Quality replacement, provenance, removal, joins, and rendering | Corpus/role assertions, reverse join tests, shared renderer test, and final focused suite | Pass |
| Quality behavioral advantage | Frozen primary and counter records, criterion scorecard, and strict gate | **Fail**: treatment misses `QR-P3`; control satisfies `QR-P1` and `QR-P2` |
| Lead-developer preservation | Current hashes equal retained inventory and prior score is cited | Partial: current bytes are known, but there is no repair-start digest that independently proves no change during repair-2 |
| Product executable-boundary assertion | Recorded deletion makes the named test fail; restoration makes it pass, then 45 focused tests pass | Pass and non-vacuous for the product assertion |
| Quality executable-boundary assertion | Literal body assertion only | Partial: no separate mutation establishes that this distinct assertion detects removal |
| Delivery checks | Logged full suite (992), whitespace, both adapter checks, static smoke, and doctor | Pass for logged automated checks; four live-client checks remain explicitly manual |
| Historical evidence / five-role release | Separate frozen repair envelope and retained lead inventory | History is preserved, but the combined five-role gate fails because both new role gates fail |

## Gate recomputation

The frozen formula is:

`parity_all_pairs AND all_four_records_successful AND all_primary_treatment_criteria_true AND all_primary_control_criteria_false AND treatment_counter_true`.

Both roles have recorded pair parity and four successful, non-error response
envelopes. Both treatment counter criteria are true. The recorded primary
booleans reproduce the failed gates:

- Product manager: `PM-P1=(true,true)`, `PM-P2=(false,false)`,
  `PM-P3=(true,true)`, where each pair is `(treatment, control)`. Therefore
  neither all treatment primary criteria true nor all control criteria false.
- Quality reviewer: `QR-P1=(true,true)`, `QR-P2=(true,true)`,
  `QR-P3=(false,false)`. The same two formula terms fail.

The machine-readable `results.json` therefore correctly marks both
`role_pass` values false, the combined release false, and merge ineligible.
The conclusion is reproducible from the immutable record hashes and does not
depend on a selective rerun or rescore.

## Vacuous or missing proof

1. The product mutation demonstrates only presence of a literal snippet. A
   wrong instruction such as “do not use cost for one unit of delay” could
   still contain both asserted snippets and pass. The frozen behavioral test
   is the necessary semantic backstop here; it did not pass.
2. The quality boundary has no mutation proof. A future change that removes or
   negates its requirement could pass the current deterministic test if it
   retains the two substrings. A targeted delete/restore mutation would make
   this local contract non-vacuous, though it would not repair the failed
   behavioral gate.
3. Lead-developer preservation is current-state evidence, not independent
   before/after proof. A change made before the retained inventory was written
   could satisfy the inventory. This does not affect the two failed gates, but
   prevents a stronger byte-for-byte preservation claim.
4. Static smoke intentionally does not prove live-client loading or runtime
   model/effort behavior. The four manual checks are correctly disclosed in
   `.flow/memory/STATE.md`; they cannot be counted as passed acceptance
   evidence.

## Acceptance disposition

**Evidence does not support `accept-review`.** Requirements 2 and 4 fail
their explicit treatment-over-control acceptance gates, and requirement 8
cannot pass while those gates remain false. The deterministic implementation
and logged delivery checks are sound enough to preserve this failed evidence
set, but passing tests do not substitute for the required behavioral
advantage. Do not merge or archive this five-role release as accepted.

The next corrective work must return to definition or re-scope the claim; a
new method, prompt, or rubric requires a new versioned envelope under the
frozen stopping rule. A quality-boundary mutation and repair-start digest are
worth adding to any later repair's proof plan.
