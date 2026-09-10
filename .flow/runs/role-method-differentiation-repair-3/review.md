# Formal review

## Review Summary

### Verdict

- **Ready to accept/archive.** Candidate production tree `T`
  `4e0a00b81c22d5a7cc2136018188e117893e9ff592813b3ccdb53be400dd8f33`
  satisfies acceptance criteria 1–10. This verdict accepts the candidate for
  source commit `C`; merge, release, refreshed installation, and post-release
  client checks remain downstream delivery gates.

### Findings

- Critical: none.
- Important: none.
- Suggestions:
  - Recompare all 29 production paths with `T` immediately before creating
    `C`, and preserve the unrelated `.flow/memory/STATE.md` delta unstaged.

The review accepts one literal validation-plan variance. The frozen doctor
baseline named five warnings, while the final normal and strict records have
four. `telemetry.claude.harvest` remains visible and changed from `warning` to
`ok` after the planned harvest refresh. Both doctor records have zero errors,
no warning was added or escalated, and release-relevant diagnostics remain
`ok`. Restoring the stale warning would make the diagnostic less accurate.

### Requirement Fit

| Criterion | Result | Evidence |
| --- | --- | --- |
| 1. Exact composed cohort | Pass | The manifest contains exactly architect, business-analyst, lead-developer, SRE, support-lead, and test-engineer as composed roles; PM and QR remain base-only. |
| 2. Retained roles and joins | Pass | All six retained role/corpus hashes match the frozen receipt; source locators, vocabulary joins, and single-section shared rendering validate. |
| 3. Three-role evidence map | Pass | The release map contains exactly architect, lead-developer, and test-engineer, with passing gates and hash-bound records. |
| 4. PM/QR base-only behavior | Pass | Their base-role hashes match, active corpora are absent, and generated adapters contain no composed Expertise section for either role. |
| 5. Failed history preservation | Pass | All 112 protected files and both protected tree digests remain byte-identical; current documentation keeps the PM/QR result failed. |
| 6. Final receipt | Pass | The independent final verifier reports 250 checks and zero failures against exact `T`. |
| 7. Determinism and mutations | Pass | The 49 focused tests pass; three negative mutations fail the intended guards, restore exact bytes, and return to a passing suite. |
| 8. Repository and runtime proof | Pass with accepted variance | The recorded full suite has 996 passes; help, diff, sync, isolated sync, runtime smoke, doctor, adapter, and native Claude/Codex checks pass. The doctor improvement is accepted above. |
| 9. Current release claims | Pass | Active documentation says three additions and six total composed roles, with no affirmative five-role-success or eight-role-composed claim. |
| 10. Bounded surface | Pass | The 29-path manifest covers the complete release range, includes inherited loader and ADR changes, and excludes the unchanged `.flow/memory/STATE.md` working delta. |

The implementation matches the approved release boundary: it retains the
three behaviorally differentiated additions, restores PM and QR to base-only
roles, preserves prior evidence, and avoids a broader admission-policy,
retrieval, routing, overlay, schema, or renderer change.

### Validation Fit

- **Observed during formal review:** all approved definition, acceptance,
  planning, validation, implementation, production, and evidence artifacts
  were read; the three independent role reviews completed; the 49 focused
  tests, 250-check frozen verifier, help regeneration check, repository diff
  check, and run verification passed.
- **Read from durable hash-bound evidence:** the 996-test full suite, user and
  isolated adapter sync/check runs, static runtime smoke, normal and strict
  doctor output, adapter readback, three mutation executions and restoration,
  and fresh Claude/Codex native-client captures.
- **Asserted and still downstream:** `C == T`, reconciliation with the current
  remote, release workflow results, `C -> R` identity, public tag/release
  readback, refreshed develop install, and repeated post-release native checks.
  None of these claims supports the candidate verdict.

### Residual Risks

- Acceptance binds only exact `T`. Any production-byte change requires renewed
  review evidence.
- Remote `main` can advance before integration; fetch and reconcile it before
  publication and rerun affected proof if the candidate changes.
- Release and install health remain unproven until all four release jobs,
  public `R` readback, develop-install refresh, doctor checks, and the second
  Claude/Codex native matrix pass.
- Any post-release doctor warning that is new, escalated, missing without
  explanation, or otherwise different from the accepted four-warning set
  requires a fresh disposition.

Formal reviewers:

- `review/formal-quality.md`: ready to accept/archive; no critical or important findings.
- `review/formal-test.md`: ready to accept/archive; doctor improvement explicitly dispositioned here.
- `review/formal-sre.md`: ready to accept/archive; downstream release and installation gates retained.
