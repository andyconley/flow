# Recovery Scope Refusal

After the approved control-plane maintenance repair at commit `94dac0c`, `recover-delivery-lead` accepted the completed Claude event trace at its actual size of 1,162,867 bytes and progressed beyond receipt evidence validation.

Recovery then sealed attempt `8aeb2ab7151a444ab28b344aa3f70f6b` as failed with `editor changed files outside the approved job scope`. The worker contains only:

- `cli/runstate.py`
- `tests/test_flow.py`
- `docs/cli-reference.md`

The sealed charter's `write_paths` are `cli/runstate.py`, `tests/test_flow.py`, `docs`, and `README.md`. The failure therefore exposes a separate path-semantics defect: a charter-authorized directory is not being treated as authorizing its safe descendants during diff validation.

The Shaper-intent implementation remains unaccepted. This receipt proves the provider-size repair worked, but a provenance-linked scope-validation repair is required before the feature can be rerun.
