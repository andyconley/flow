# Quality review: role-method differentiation repair

## Review Summary

### Verdict

- Needs refinement.

The product changes and final delivery checks are mechanically sound, and the
previous results, mutation, validation, and handoff evidence gaps are now
substantially closed. The frozen behavioral evidence still fails the approved
stopping rule for both repaired roles. Acceptance criteria 2, 4, and therefore
8 fail, so the combined five-role change must not merge or release as a proven
behavioral improvement.

## Frozen scorecard

I read all eight raw JSON responses and independently compared them with the
frozen scorecards. Their SHA-256 values match `repair-2/results.json`, every
record is a successful non-error envelope, and the manifest hash recorded in
the results is current.

### Product-manager

| Predicate | Treatment | Control | Evidence |
| --- | --- | --- | --- |
| `PM-P1` classify cliff, gradual, and flat shapes | **true** | **true** | Treatment's table names `Cliff at wk 4`, `Linear erosion`, and `Flat within horizon`. Control describes the hard deadline/all-or-nothing renewal, onboarding that `decays $25,000/week`, and flat dashboard value. |
| `PM-P2` compare each delay cost divided by duration | **false** | **false** | Treatment writes that compliance is `not comparable on a rate basis` instead of calculating the frozen `$240,000 / 4 = $60,000`; control never calculates or explicitly compares all three required ratios. |
| `PM-P3` sequence from the comparison and reject importance-only order | **true** | **true** | Both order renewal, onboarding, dashboard and explicitly explain why stated importance or total value should not put the dashboard first. |
| `PM-C1` avoid invented urgency in the flat counter-case | **true** | **true** | Both decline to manufacture a cost-of-delay ranking and ask for a real discriminator. Control is informational for this counter predicate. |

The treatment misses `PM-P2`, and the control satisfies `PM-P1` and `PM-P3`.
Either condition fails the strict role gate; both occurred.

### Quality-reviewer

| Predicate | Treatment | Control | Evidence |
| --- | --- | --- | --- |
| `QR-P1` state the plausible constraint explanation | **true** | **true** | Both state that a database constraint could reject the unsupported value before commit. |
| `QR-P2` rule it out with schema and persisted result | **true** | **true** | Both cite the schema's missing value-set constraint and the observed `turbo` value after `ValueError`. |
| `QR-P3` file Critical only after that chain | **false** | **false** | Both declare/file the Critical before presenting their alternative-explanation analysis. The frozen `only then` order is not met. |
| `QR-C1` keep the unresolved counter-case below Critical | **true** | **true** | Both retain an Important finding, request repository/schema/transaction/test proof, and avoid a confirmed Critical. Control is informational for this counter predicate. |

The treatment misses `QR-P3`, and the control satisfies `QR-P1` and `QR-P2`.
Again, either condition fails the strict role gate and both occurred.

### Stopping-rule disposition

The frozen formula requires successful parity-controlled records, every primary
treatment predicate true, every primary control predicate false, and the
treatment counter true. The record/parity and counter conditions pass. The two
primary conditions fail for each role, so both `role_pass` values and the
combined five-role gate are **false**. The immutable results correctly prohibit
selective reruns or rescoring; a changed method, prompt, fixture, or rubric needs
a new versioned envelope.

## Findings

### Critical

- `docs/evidence/role-method-differentiation/repair-2/results.json` and
  acceptance criteria 2 and 4: the frozen behavioral comparison disproves the
  required treatment-only advantage for both roles. A plausible alternative
  explanation is that the controls merely reached the same conclusions through
  generic reasoning without performing the selected methods. The raw text rules
  that out: product control performs shape classification and the
  importance-versus-delay sequence; quality control states the constraint
  hypothesis and rejects it with both discriminating facts. The treatments also
  miss `PM-P2` and `QR-P3`. Preserve repair-2 as failed. Return to definition to
  choose a more distinctive method or explicitly conclude that the unchanged
  bodies already provide enough of these methods; do not claim differentiation
  from this evidence.

### Important

- None beyond the release-blocking behavioral result above.

### Suggestions

- A successor product fixture should provide activation onboarding's starting
  value or prohibit total-captured-value claims. Both primary arms calculate a
  total that the supplied fixture cannot support. This does not alter the frozen
  predicate scores.

## Requirement Fit

| Acceptance criterion | Disposition | Evidence strength |
| --- | --- | --- |
| 1. Product replacement/source/superseded removal | **pass** | **Observed/read:** current role/corpus hashes match the frozen treatment sources; one Reinertsen 2009 chapter 2 entry and competency remain; superseded id is absent. Publication verification is read from the evidence record, not independently repeated. |
| 2. Product treatment advantage and safe counter | **fail** | **Observed:** treatment fails `PM-P2`; control passes `PM-P1` and `PM-P3`; counter passes. |
| 3. Quality replacement/source/superseded removal | **pass** | **Observed/read:** current role/corpus hashes match the frozen treatment sources; one Heuer 1999 chapter 8 entry and competency remain; both superseded ids are absent. Publication verification is read from the evidence record, not independently repeated. |
| 4. Quality treatment advantage and calibrated counter | **fail** | **Observed:** treatment fails `QR-P3`; control passes `QR-P1` and `QR-P2`; counter passes. |
| 5. Preserve lead-developer pass | **pass with stated evidence limit** | **Observed/read:** `preserved-lead-developer.json` inventories the current role, corpus, design, four transcript hashes, and prior passing score; each hash matches its file. **Asserted:** byte-for-byte non-mutation since repair start, because no repair-start digest was frozen. The validation record now states that limit accurately. |
| 6. Deterministic and mutation proof | **pass** | **Observed:** current 45-test focused suite passes. **Read:** the mutation record says removal caused the named test to exit 1, exact restoration made it pass, then all 45 passed. |
| 7. Final-tree delivery checks | **pass with declared manual follow-up** | **Observed in this review:** 45 focused and 992 full tests pass, `git diff --check` passes, both adapter checks are current, runtime smoke reports zero failures and four manual checks, and doctor passes with unrelated notices. |
| 8. Preserved history and combined five-role result | **fail** | **Observed/read:** historical records remain separate and repair-2 now has immutable scored results; architect, test-engineer, and lead-developer are recorded as prior passes, but product-manager and quality-reviewer fail, so the required five-role result does not exist. |

## Validation Fit

- **Observed by this reviewer:** all eight raw record hashes match
  `results.json`; manifest SHA-256 is
  `8b8b8138c84cf111aa07942ad88fc68db16566f92aac38c230fdf9e384d2ed01`;
  final product and quality source hashes match the frozen manifest; 45 focused
  tests pass; 992 full tests pass in 92.073 seconds; whitespace, Claude/Codex
  adapter checks, static runtime smoke, and doctor pass.
- **Read:** exact replacement ids and joins, the mutation failure/restoration
  record, preserved prior behavioral records, source locators, updated evidence
  summaries, scored result, handoff, and findings reconciliation.
- **Author-asserted:** external publication verification and byte-for-byte
  lead-developer non-mutation during repair-2. The current retained bytes and
  prior passing score are independently inventoried and match.
- **Declared follow-up:** four live-client command/agent load checks remain in
  `.flow/memory/STATE.md`. Static checks do not claim to satisfy them, and they
  are not the cause of the acceptance failure.

Correctness, clarity, structural fit, safety, and verifiability were assessed.
The content change is clear and local, and it introduces no application
security, persistence, or rollout hazard. Commit/PR convention review does not
apply because the work remains uncommitted.

## Resolved Since Initial Review

- `repair-2/results.json` now records criterion-level scores and all eight raw
  response hashes.
- The top-level evidence summaries, validation results, handoff, and findings
  reconciliation now describe repair-2 and retain the earlier failed history.
- `mutation-check.md` now records the targeted failure and exact restoration.
- Final-tree focused/full tests, whitespace, adapter, runtime-smoke, doctor, and
  production-hash checks are current.
- `preserved-lead-developer.json` now inventories every retained lead source and
  evidence file while explicitly stating that no repair-start digest exists;
  validation no longer overstates the non-mutation proof.
- `behavioral-scoring-repair.md` now names the existing full
  `docs/evidence/role-method-differentiation/repair-2/execution-results.json`
  path, so its hash-provenance claim resolves.

## What's Done Well

- The implementation keeps each repaired role to one source-traced corpus entry
  and the minimum matching role-body instruction.
- Exact-id, reverse-join, composed-manifest, and shared-renderer assertions make
  the deterministic composition proof specific rather than keyword-based.
- The evidence process preserves negative results and applies the stopping rule
  without outcome-driven relaxation. The failure is clear, reproducible, and
  useful for the next definition decision.
- Both counter-cases behave safely: product does not invent urgency, and quality
  does not promote unresolved evidence to Critical.

## Residual Risks

- The base role bodies already elicit much of both selected methods, so the new
  corpus entries may increase prompt volume without producing a reliable
  behavior gain.
- The product fixture elicited unsupported total-value arithmetic from both
  arms; a future comparison could reward a target sequence while overlooking a
  reasoning defect unless the fixture closes that ambiguity.
- Lead-developer's current retained files and prior pass are reproducible; only
  the repair-period non-mutation claim remains dependent on implementation
  history because a repair-start digest was not frozen.
