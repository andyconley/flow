# Validation results

## Verdict

The production surface and deterministic delivery checks pass. The frozen
behavioral acceptance checks fail for product-manager and quality-reviewer.
This implementation is ready for formal review, but the five-role expansion is
not eligible for merge or release.

## Deterministic and delivery evidence

| Check | Result | Evidence |
| --- | --- | --- |
| Focused composition suite | pass | **Observed:** 45 tests pass with Python 3.12 after the final restoration. |
| Mutation check | pass | **Observed:** deleting the selected product instruction makes the named executable-boundary test fail with exit 1; restoring the exact lines makes it and the 45-test suite pass. See `docs/evidence/role-method-differentiation/repair-2/mutation-check.md`. |
| Full suite | pass | **Observed:** 992 tests pass in 91.696 seconds in the root run and 92.073 seconds in independent review against the final production hashes. |
| Whitespace | pass | **Observed:** `git diff --check` exits 0. |
| Claude adapter | pass | **Observed:** user sync completed; `flow sync claude --user --check` reports current. |
| Codex adapter | pass | **Observed:** user sync completed; `flow sync codex --user --check` reports current. |
| Static runtime smoke | pass with manual follow-up | **Observed:** `flow runtime smoke --target all --json` reports `ok: true`, `failed: 0`, and four manual checks. |
| Doctor | pass with unrelated notices | **Observed:** `flow doctor` confirms the develop source, clean Claude/Codex sync, 13 of 13 agents, and FTS5 availability. Historical archive gaps and one project-adoption decision remain outside this repair. |

The four manual checks remain recorded in `.flow/memory/STATE.md`: load
`flow-status` and inspect `support-lead` model/effort in each live client. Static
checks do not claim that evidence.

The final product-manager and quality-reviewer role/corpus hashes match the
treatment source hashes frozen in `repair-2/manifest.json`. The manifest itself
still hashes to `8b8b8138c84cf111aa07942ad88fc68db16566f92aac38c230fdf9e384d2ed01`.

## Behavioral evidence

| Role | Treatment primary | Control primary | Treatment counter | Gate |
| --- | --- | --- | --- | --- |
| Product manager | fails `PM-P2` | passes `PM-P1`, `PM-P3` | pass | **fail** |
| Quality reviewer | fails `QR-P3` | passes `QR-P1`, `QR-P2` | pass | **fail** |

**Observed:** all eight live-client records completed without client error and
every pair met invocation parity. **Observed by independent review:** the
criterion-level scores above. `repair-2/results.json` binds them to the raw
response hashes. The stopping rule requires every treatment primary item to be
true and every control primary item to be false. Ties and partial control
overlap fail.

## Acceptance criteria

| Criterion | Result |
| --- | --- |
| 1. Product replacement, source, and superseded removal | pass |
| 2. Product behavioral advantage and safe counter | fail |
| 3. Quality replacement, source, and superseded removal | pass |
| 4. Quality behavioral advantage and calibrated counter | fail |
| 5. Preserve lead-developer contract, corpus, and evidence | pass by retained source/evidence inspection; `repair-2/preserved-lead-developer.json` records the current hashes and prior score, but the absence of a repair-start hash leaves byte-for-byte non-mutation author-asserted |
| 6. Deterministic and mutation proof | pass |
| 7. Final-tree delivery checks | pass; four declared manual checks remain follow-up evidence |
| 8. Preserve history and establish combined five-role pass | fail because two role gates remain false |

## Limits

- The product fixture permits marginal delay comparison but does not supply an
  initial onboarding value; both arms made unsupported total-value claims.
- The unchanged role bodies already elicit much of each selected method. Added
  corpus text may therefore add prompt volume without a reliable behavior gain.
- Source verification establishes edition and locator provenance. It does not
  substitute for behavioral evidence.
