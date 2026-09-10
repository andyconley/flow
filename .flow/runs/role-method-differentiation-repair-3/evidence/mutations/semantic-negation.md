# Mutation receipt: lead-developer semantic negation

- Target: `scaffolds/default/agents/lead-developer.md`
- Mutation: change `First classify reversibility, blast radius, and existing
  test coverage` to `Do not First classify reversibility, blast radius, and
  existing test coverage`.
- Preserved vocabulary: `First`, `classify`, `reversibility`, `blast
  radius`, and `existing test coverage` remain in the mutated text.
- Original SHA-256:
  `2dc53fe1b1b5b671ddfddf1fc666dd6280d954282c34621cce626a375f22c513`
- Mutated SHA-256:
  `5371f39d84c478452aa297d3f1a4480500f451ad8453eb82feba8f8d3f914851`
- Started: 2026-09-10T11:50:21Z
- Ended: 2026-09-10T11:50:21Z
- Failing command:
  `/opt/homebrew/bin/python3.12 -m unittest tests.test_expertise_composition.ShippedCorpusTests.test_lead_developer_obligation_is_positive_and_uses_short_form`
- Expected exit: nonzero
- Observed exit: 1
- Raw failing log: `evidence/logs/mutation-semantic-negation-fail.log`
- Diagnostic excerpt: the required positive regex beginning
  `^First classify reversibility` did not match the body containing
  `Do not First classify reversibility`.
- Restoration: restore the exact positive sentence with `apply_patch`.
- Restored SHA-256:
  `2dc53fe1b1b5b671ddfddf1fc666dd6280d954282c34621cce626a375f22c513`
- Post-restoration command:
  `/opt/homebrew/bin/python3.12 -m unittest tests.test_expertise_composition`
- Post-restoration result: 49 tests passed, exit 0,
  2026-09-10T11:50:42Z.
- Raw restoration log:
  `evidence/logs/mutation-semantic-negation-restored.log`

Verdict: observed pass. The guard tests obligation direction, rather than
passing when the former keywords survive inside a negated instruction.
