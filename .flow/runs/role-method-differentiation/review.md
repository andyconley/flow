# Review: role-method differentiation

## Review Summary

### Verdict

- Needs refinement.

The replacement methods are source-traced, correctly composed, and covered by
passing deterministic delivery checks. They do not meet the approved behavioral
acceptance condition. Product-manager and quality-reviewer both fail the frozen
treatment-over-control rule, so the combined five-role release remains blocked.

### Findings

- **Critical:** Neither replacement method demonstrates the required
  treatment-only behavior. One alternative explanation is that the unchanged
  controls reached similar conclusions through generic reasoning while only
  the treatments used the named methods. The frozen responses rule that out:
  the product control already identifies the three decay shapes and sequences
  by delay sensitivity, while the quality control already tests and rules out
  the database-constraint explanation. Product treatment also misses `PM-P2`,
  and quality treatment files its Critical before completing `QR-P3`'s required
  evidence chain. Acceptance criteria 2 and 4 therefore fail, which makes the
  combined criterion 8 fail.
- **Important:** Lead-developer's current role, corpus, design, and four prior
  transcript hashes match the retained inventory, but no repair-start digest
  exists. Criterion 5 has current-state and historical evidence, not an
  independently verified before-and-after byte comparison for repair-2.
- **Suggestions:** In a successor evidence envelope, supply onboarding's
  starting value or prohibit total-value claims in the product fixture. Add a
  quality-reviewer delete-and-restore mutation and freeze preservation digests
  before any edits. These strengthen proof but do not repair the failed
  behavioral gates.

### Requirement Fit

| Criterion | Result | Evidence judgment |
| --- | --- | --- |
| 1. Product replacement, source, removal | Pass | **Observed:** exact replacement id, competency join, role rendering, and absence of the superseded id. **Read:** the source record verifies the Reinertsen edition and Chapter 2 economic-view locator and identifies duration weighting as Flow's operational adaptation. |
| 2. Product differentiated behavior | Fail | **Observed:** treatment passes `PM-P1`, `PM-P3`, and `PM-C1`, but misses `PM-P2`; control also passes `PM-P1` and `PM-P3`. Both strict predicates fail. |
| 3. Quality replacement, source, removal | Pass | **Observed:** exact replacement id, joins, rendering, and absence of both superseded ids. **Read:** the source record verifies the Heuer edition and Chapter 8 locator. |
| 4. Quality differentiated behavior | Fail | **Observed:** treatment passes `QR-P1`, `QR-P2`, and `QR-C1`, but misses `QR-P3`; control also passes `QR-P1` and `QR-P2`. Both strict predicates fail. |
| 5. Preserve lead-developer | Partial | **Observed:** all retained current hashes match and the earlier score remains a pass. **Asserted:** those bytes never changed during repair-2; no repair-start digest proves the history independently. |
| 6. Deterministic contracts and mutation | Pass | **Observed:** 45 focused tests pass. **Read:** removing the selected product instruction failed its named test; restoration returned the suite to green. |
| 7. Final-tree delivery checks | Pass | **Observed in formal review:** focused tests and whitespace check pass. **Read from frozen delivery evidence:** 992 full tests, both adapter checks, static runtime smoke, and doctor pass. Four live-client checks remain explicitly manual and are not counted here. |
| 8. Historical evidence and five-role release | Fail | **Observed/read:** the original and repair-2 evidence sets remain separate, and the three prior passing roles remain cited. The two replacement role gates are false, so no combined five-role pass exists. |

### Validation Fit

- **Observed by the formal reviewers:** all eight raw repair-2 responses were
  read; their hashes, the manifest digest, current treatment-source hashes, and
  frozen control hashes match the recorded evidence. Recomputing the frozen
  formula yields `false` for both roles. The 45-test focused suite and
  `git diff --check` pass.
- **Read from retained evidence:** the 992-test suite, adapter checks, static
  runtime smoke, doctor result, mutation record, source-verification record,
  prior role scores, and historical transcripts.
- **Asserted rather than independently observed:** byte-for-byte
  lead-developer non-mutation throughout repair-2 and the external publication
  lookup process. Current citations and file hashes are present.
- The quality-reviewer and test-engineer independently reached the same
  disposition: the implementation evidence is internally consistent, but it
  does not support `accept-review`.
- The acceptance-stage orchestration validator passes with no findings. The run
  remains in `reviewing`; no acceptance transition was executed.

### Residual Risks

- Shipping the two additions would add prompt material without demonstrated
  behavioral differentiation because the unchanged role bodies already produce
  much of the selected behavior.
- The product primary fixture permits unsupported total-value arithmetic because
  onboarding's initial value is absent.
- Literal body assertions can survive semantically negated wording. Behavioral
  proof remains the required backstop, and that proof currently fails.
- Static smoke does not prove live-client loading or model behavior; the four
  manual checks remain separate follow-up work.

`accept-review` must not run. Preserve repair-2 as failed evidence and return to
`flow-define` to select a more distinctive method or narrow the release claim.
