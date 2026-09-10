# Mutation receipt: product-manager reintroduction

- Target: `scaffolds/default/flow.toml`
- Mutation: add `generation_mode = "composed"` to the framework
  `product-manager` declaration while its baseline corpus remains absent.
- Original SHA-256:
  `c17e5b7905e02ae26f2173221addb54ef5bcc5c848a53a66d8a47683b237c9d1`
- Mutated SHA-256:
  `c266357cff2d6dcdac0fdd21d9aa092b1c18639b3719f3317da49b9a2be71822`
- Started: 2026-09-10T11:48:51Z
- Ended: 2026-09-10T11:48:51Z
- Failing command:
  `/opt/homebrew/bin/python3.12 -m unittest tests.test_expertise_composition.ShippedCorpusTests.test_manifest_marks_exactly_the_shipped_roles_composed tests.test_expertise_composition.ShippedCorpusTests.test_inactive_roles_match_frozen_base_and_have_no_composed_surface`
- Expected exit: nonzero
- Observed exit: 1
- Raw failing log: `evidence/logs/mutation-pm-fail.log`
- Diagnostic excerpt: `Items in the first set but not the second:
  'product-manager'`; the inactive-role assertion also reports
  `'composed' == 'composed'` for `product-manager`.
- Restoration: remove the injected declaration with `apply_patch`.
- Restored SHA-256:
  `c17e5b7905e02ae26f2173221addb54ef5bcc5c848a53a66d8a47683b237c9d1`
- Post-restoration command:
  `/opt/homebrew/bin/python3.12 -m unittest tests.test_expertise_composition`
- Post-restoration result: 49 tests passed, exit 0,
  2026-09-10T11:49:11Z–11:49:12Z.
- Raw restoration log: `evidence/logs/mutation-pm-restored.log`

Verdict: observed pass. The exact cohort and inactive-role guards reject PM
reintroduction, then pass only after the original bytes are restored.
