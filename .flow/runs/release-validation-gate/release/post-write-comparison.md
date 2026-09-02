# Post-write Comparison

The hosted publication produced exactly the intended shared-state delta. No
unexpected delta was observed.

| Contract | Expected | Observed | Result |
|---|---|---|---|
| Validated source | `e05178b78420db53c3f7431448e1d188cc958441` | Workflow head and generated commit parent match | passed |
| Version and tag | One next minor release, `v0.22.0` | `v0.22.0` exists at `f5f4556` | passed |
| Generated commit | One changelog-only child of source | Sole parent is `e05178b`; only `CHANGELOG.md` changed | passed |
| GitHub release | Published, non-draft, non-prerelease, non-empty notes | Published at `2026-09-02T12:53:11Z`; notes digest matches plan | passed |
| Public consumption | Fresh install and upgrade from `v0.21.0` | Both hosted public checks passed | passed |
| Runtime surfaces | Setup, sync, doctor, static smoke, representative CLI | All hosted public checks passed | passed |

The recovery path was not exercised because publication and public verification
succeeded. The two earlier hosted attempts failed before publication and left
the shared repository unchanged, confirming the gate failed closed.
