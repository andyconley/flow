# Mutation check

The deterministic executable-boundary test is non-vacuous.

- Mutation: temporarily remove the product-manager instruction containing
  `cost for one unit of delay` from
  `scaffolds/default/agents/product-manager.md`.
- Command:
  `/opt/homebrew/bin/python3.12 -m unittest tests.test_expertise_composition.ShippedCorpusTests.test_role_bodies_keep_the_new_executable_boundaries`
- Observed result: exit 1. The product-manager subtest failed because the
  required snippet was absent.
- Restoration: restore the exact three instruction lines.
- Observed result after restoration: the named test passed, followed by all 45
  focused expertise-composition tests.

The mutation changed only the selected instruction and was not retained.
