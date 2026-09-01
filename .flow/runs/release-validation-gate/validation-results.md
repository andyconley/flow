# Validation Results

## Current verdict

Implementation, failure-path validation, mutation proof, and independent
pre-publication reviews pass. The retained candidate artifact is superseded and
must be regenerated for the final exact SHA before publication. Public-artifact
readback remains pending by design.

## Automated evidence

| Check | Result | Validated against | Transfer verdict |
|---|---|---|---|
| Focused release/security/recovery tests | 50 passed | changed source through `ebdaf02` | transfers |
| Full unittest discovery | 767 passed | changed source at `ebdaf02` | transfers |
| Generated help | passed | changed source | transfers |
| Release staging/imports | passed | local candidate at exact SHA | transfers |
| Fresh install | passed | local-only predicted tag | transfers for tag selection and installed content; hosted network unverified |
| Upgrade | passed | previous and candidate local tags | transfers for update/staging/atomic swap; hosted network unverified |
| Setup and both sync checks | passed | isolated candidate home | transfers for static generated surfaces |
| Doctor | passed under named warning policy | isolated candidate home | transfers for machine/static health; live-client and telemetry history unverified |
| Runtime smoke | passed | isolated candidate home | transfers for static checks; live client checks remain manual |
| Representative CLI | passed | isolated candidate home and local remote | transfers for CLI behavior; public remote unverified |

## Failure and mutation checks

- All thirteen stable candidate check IDs were injected as failures through the
  real candidate runner. Each failing check was recorded, later checks were
  `not_run`, and the resulting evidence could not invoke the fake publisher.
- The modeled remote branch, tag list, release list, and changelog remained
  unchanged for each rejected evidence position.
- The eight required workflow mutations were detected by named findings:
  `publish-dependency`, `analysis-credential`, `exact-checkout`,
  `evidence-digest`, `failure-bypass`, `no-release-publish`,
  `public-failure-classification`, and `notes-shell-interpolation`.
- A real edit removing the publish dependency made
  `test_workflow_has_no_named_contract_findings` fail with
  `publish-dependency`; the edit was restored and the test passed.
- Temporary-remote integration tests reject moved `main`, a moved previous
  release tag, and an already-existing candidate tag.

## External mutation

Not run. `origin/main`, `v0.22.0`, the GitHub release, and `CHANGELOG.md` remote
state have not been changed. The dispatch baseline must be refreshed immediately
before any write.
