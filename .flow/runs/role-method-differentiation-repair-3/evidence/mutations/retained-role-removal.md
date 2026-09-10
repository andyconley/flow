# Mutation receipt: retained test-engineer removal

- Target: `scaffolds/default/flow.toml`
- Mutation: remove `generation_mode = "composed"` from the framework
  `test-engineer` declaration while retaining its corpus.
- Original SHA-256:
  `c17e5b7905e02ae26f2173221addb54ef5bcc5c848a53a66d8a47683b237c9d1`
- Mutated SHA-256:
  `8d412eccd4fb240dec4c8437fc5fdd840584655450134c2c78b79d95727d19ed`
- Started: 2026-09-10T11:49:36Z
- Ended: 2026-09-10T11:49:36Z
- Failing command:
  `/opt/homebrew/bin/python3.12 -m unittest tests.test_expertise_composition.ShippedCorpusTests.test_manifest_marks_exactly_the_shipped_roles_composed`
- Expected exit: nonzero
- Observed exit: 1
- Raw failing log: `evidence/logs/mutation-retained-role-fail.log`
- Diagnostic excerpt: `Items in the second set but not the first:
  'test-engineer'`.
- Restoration: reinsert the exact declaration with `apply_patch`.
- Restored SHA-256:
  `c17e5b7905e02ae26f2173221addb54ef5bcc5c848a53a66d8a47683b237c9d1`
- Post-restoration command:
  `/opt/homebrew/bin/python3.12 -m unittest tests.test_expertise_composition`
- Post-restoration result: 49 tests passed, exit 0,
  2026-09-10T11:49:57Z.
- Raw restoration log:
  `evidence/logs/mutation-retained-role-restored.log`

Verdict: observed pass. Retained corpus data cannot substitute for activation;
the exact cohort guard fails until the declaration is restored.
