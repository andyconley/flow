# Formal acceptance review: role-method differentiation

## Review Summary

### Verdict

- Needs refinement.

The narrow product-manager and quality-reviewer changes are structurally sound,
source-traced, rendered through the shared path, and covered by passing
deterministic checks. They do not satisfy the approved behavioral release
condition. Under the frozen stopping rule, acceptance criteria 2, 4, and 8 fail;
the five-role release must remain blocked.

### Findings

- **Critical — the required treatment-only behavioral advantage is absent for
  both repaired roles.** A plausible explanation under which the implementation
  is correct is that the controls reached the right conclusions through generic
  reasoning without actually performing the selected methods, while the
  treatments supplied the distinctive method. The raw responses rule that out.
  Product control classifies the deadline, gradual decay, and flat value shapes,
  then sequences renewal, onboarding, and dashboard by delay sensitivity rather
  than importance; product treatment also refuses the frozen `$240,000 / 4 =
  $60,000` comparison as "not comparable on a rate basis." Quality control
  states the database-constraint explanation and rules it out with the missing
  schema constraint and persisted `turbo` observation; quality treatment declares
  the Critical before presenting that same chain. Thus treatment misses `PM-P2`
  and `QR-P3`, while control satisfies `PM-P1`, `PM-P3`, `QR-P1`, and `QR-P2`.
  This directly contradicts acceptance criteria 2 and 4 and makes criterion 8's
  combined pass impossible. Preserve repair-2 as failed and return to definition
  to choose a more distinctive method or narrow the claim to behavior already
  supplied by the unchanged bodies. Do not selectively rerun or rescore this
  envelope.
- **Important — lead-developer preservation is not independently proven across
  repair-2.** The current role, corpus, design, and four prior response hashes
  match `preserved-lead-developer.json`, and the prior evidence records a passing
  gate. A repair-start digest was never frozen, so the stronger claim that those
  bytes remained unchanged throughout this repair is author-asserted. Treat
  acceptance criterion 5 as partial evidence and freeze before/after digests at
  the start of any successor repair.
- **Suggestions — strengthen the next evidence envelope.** The product primary
  fixture omits onboarding's starting value, yet both arms claim a total captured
  value; provide the starting value or prohibit total-value claims. A later
  mutation plan can also delete and restore the quality-reviewer instruction,
  although acceptance criterion 6's singular mutation requirement is already
  met by the recorded product mutation.

### Requirement Fit

| Acceptance criterion | Result | Assessment |
| --- | --- | --- |
| 1. Product replacement, verified source/locator, and superseded removal | **Pass** | **Observed:** the shipped corpus has exactly the replacement id and competency; the superseded id is absent; current role/corpus hashes match the frozen treatment sources. **Read:** the source-verification record supports the Reinertsen 2009 edition and Chapter 2 locator. |
| 2. Product treatment advantage and safe counter | **Fail** | **Observed:** treatment passes `PM-P1`, `PM-P3`, and `PM-C1` but fails `PM-P2`; control also passes `PM-P1` and `PM-P3`. The strict treatment and control predicates both fail. |
| 3. Quality replacement, verified source/locator, and superseded removal | **Pass** | **Observed:** the shipped corpus has exactly the replacement id and competency; both superseded ids are absent; current role/corpus hashes match the frozen treatment sources. **Read:** the source-verification record supports the Heuer 1999 edition and Chapter 8 locator. |
| 4. Quality treatment advantage and calibrated counter | **Fail** | **Observed:** treatment passes `QR-P1`, `QR-P2`, and `QR-C1` but fails `QR-P3`; control also passes `QR-P1` and `QR-P2`. The strict treatment and control predicates both fail. |
| 5. Preserve lead-developer contract, corpus, and prior evidence | **Partial** | **Observed:** all seven current hashes match the retained inventory and the prior score records a pass. **Asserted:** no lead-developer bytes changed during repair-2; no repair-start digest exists to verify that history independently. |
| 6. Deterministic contracts, joins, rendering, and mutation proof | **Pass** | **Observed:** all 45 focused tests pass, including exact replacement ids, superseded-id rejection, composed-role manifest, joins, body snippets, and shared rendering. **Read:** the mutation record reports that deleting the selected product instruction failed the named test, followed by restoration and a passing suite. |
| 7. Final-tree delivery checks | **Pass** | **Observed:** the focused suite and `git diff --check` pass in this review. **Read:** the final-tree log records 992 passing tests, current Claude/Codex adapter checks, runtime smoke with zero failures, and a passing doctor run. Four explicitly manual live-client checks remain follow-up and are not claimed as this criterion. |
| 8. Preserve failed history and establish the combined five-role pass | **Fail** | **Observed/read:** the original evidence remains separate, repair-2 is separately frozen, and architect, test-engineer, and lead-developer retain recorded passes. Product-manager and quality-reviewer fail, so the required combined result does not exist. |

### Validation Fit

- **Observed in this review:** all eight raw repair-2 responses were read; each
  is a successful one-turn result envelope. Their SHA-256 values, the manifest
  digest, four current treatment-source hashes, and two `git show` control-body
  hashes match the frozen records. The frozen role-pass formula recomputes to
  false for both roles. The focused 45-test suite and `git diff --check` pass.
- **Read from retained evidence:** the 992-test full-suite log, adapter checks,
  static runtime smoke, doctor output, mutation failure/restoration record,
  source-verification record, earlier role scores, and historical transcripts.
- **Author-asserted:** byte-for-byte lead-developer non-mutation during repair-2
  and the external publication verification process. The current publication
  citations and retained file hashes are present, but this review did not repeat
  external research.
- Correctness, clarity, structural fit, safety, and verifiability were assessed.
  The content and test changes are local and readable, and no application data,
  authorization, secret-handling, performance, or operational surface changes.
  Commit/PR convention review does not apply because the work is uncommitted.

### Residual Risks

- The unchanged role bodies already produce much of both selected behavior, so
  shipping the added prompt material would create cost without demonstrated
  differentiation.
- Four live-client loading/model checks remain recorded separately. They do not
  explain or repair the behavioral failures.
- The product fixture's unsupported total-value arithmetic can distract later
  scoring unless a successor fixture closes that input gap.

### Acceptance Disposition

`accept-review` **must not run**. The approved release relationship requires both
replacement methods to pass, and the immutable evidence records both role gates
as false. The appropriate next lane is `flow-define`, with repair-2 retained as
failed evidence.
