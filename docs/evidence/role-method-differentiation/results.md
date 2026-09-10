# Behavioral result record

All control records were rerun from the pre-change `HEAD` role bodies. All
twelve raw JSON records completed without error. Independent review must score
the distinctive rubric items before a release disposition; no merge is implied
by transcript capture or deterministic validation.

## Independent scoring

| Role | Primary | Counter | Gate | Disposition |
| --- | --- | --- | --- | --- |
| Product manager | tie | pass | fail | The unchanged body already used decay and reversibility; treatment only made the success condition more resolvable. |
| Quality reviewer | tie | pass | fail | The unchanged body already found the omission; treatment improved evidence labels and critical calibration only. |
| Lead developer | pass | pass | pass | Treatment used the required short form for the local reversible fix and retained full planning for the public stateful migration. |

The release requires all three gates to pass. It therefore fails and must not
merge. The complete independent analysis is at
`.flow/runs/role-method-differentiation/research/behavioral-scoring.md`.

## Repair-2 amendment

The separately frozen replacement run kept the passing lead-developer result
and reran only product-manager and quality-reviewer with their approved narrow
methods. All eight records completed with treatment/control parity.

| Role | Treatment primary | Control primary | Treatment counter | Gate |
| --- | --- | --- | --- | --- |
| Product manager | Missed `PM-P2` | Passed `PM-P1` and `PM-P3` | pass | fail |
| Quality reviewer | Missed `QR-P3` | Passed `QR-P1` and `QR-P2` | pass | fail |

The strict rule required every treatment primary predicate to pass and every
control primary predicate to fail. Both replacements therefore fail. The
criterion-level scores and raw-response hashes are preserved in
`repair-2/results.json`; no earlier transcript or score was rewritten.
