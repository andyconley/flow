# Three full production CLI live smoke checks

All three intended end-to-end outcomes passed on the independently reviewed candidate. Real existing local Ollama model and stock OpenHands sessions were used; no SDK mocks. Frozen criteria, source and configuration hashes stayed unchanged. There was one initial expected failed check and one targeted behavior repair per case, no review-output retries, and no repeated campaign.

| Case | Actual final outcome | Held checks | Seconds | Observed SDK output tokens |
|---|---|---|---:|---:|
| hardcoded-shortcut | blocked; review REJECT | expected failure: shortcut rejected | 457.24 | 17,990 |
| ordinary | review_accepted; review ACCEPT | pass | 257.81 | 8,418 |
| repair | review_accepted; review ACCEPT | pass | 212.84 | 8,316 |

Ordinary work and legitimate import repair reached actual CLI final acceptance. The repair retained the addition assertion, received an actual independent EQUIVALENT review, recorded a version-bound receipt through the CLI and passed held checks. The hardcoded answer passed the approved sample gate, but live independent review REJECTed it, held physics checks failed and actual CLI final approval returned nonzero. The host then blocked it. All three `flow run verify` commands returned zero.

The producer itself had already chosen constant0.5 in the shortcut case; the planned host injection wrote that same fixture. The pre-injection source and all model actions remain retained. The negative reviewer also made an inaccurate import/equivalence annotation: final check.py was identical to the frozen test and no equivalence receipt was issued. That annotation did not permit acceptance or change criteria. It is a remaining semantic-review limitation, not a passing claim about every reviewer statement.

This is a three-case functional smoke, not an efficiency comparison. Observed SDK metrics were reconciled using the existing importer/normalizer into an experiment-local ledger with no import/normalization failures. SDK counts may be provider reports or adapter fallback; authoritative whole-team totals, active host overhead, human review time and actual bills remain unknown. No invented token ceiling or matched-token claim.

Preflight, raw CLI stdout/stderr, command timings, run/event/verification records, review artifacts, SDK persistence, external scripts/results and failed initial checks are retained outside the repository in `flow-cli-smoke-20261015`. `summary.json` binds result and review hashes. No extra round or production fix was introduced during these checks. Source remains the independently reviewed version. Passing this smoke does not establish coding gains or erase the earlier R2 unmet rework target.
