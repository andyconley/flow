# Validation Results

## Verdict

Passed. The exact candidate was validated, published as `v0.22.0`, and verified
through public consumer paths. The observed shared-state delta matches the
approved release contract and no recovery action was required.

## Evidence

| Check | Result | Validated against | Transfer verdict |
|---|---|---|---|
| Hosted workflow | 4 jobs passed | source `e05178b` | direct |
| Candidate gate | 13 checks passed | exact checked-out source | direct |
| Full unittest discovery | 770 passed | exact checked-out source in isolated home | direct |
| Focused release suites | 52 passed | exact checked-out source | direct |
| Failure injection | 13 positions rejected | real candidate runner and fake publication boundary | direct for gate behavior |
| Workflow mutation suite | 8 required mutations rejected | workflow contract | direct |
| Real mutation check | publish dependency removal failed named test | changed workflow, then restored | direct |
| Git tag and generated commit | passed | public `v0.22.0` | direct |
| GitHub release and notes | passed | published release and planned digest | direct |
| Public fresh install and upgrade | passed | GitHub-hosted `v0.22.0` | direct |
| Setup, sync, doctor, runtime smoke, CLI | passed | public installation | direct for non-interactive surfaces |
| Live client discovery/model routing | not run | requires interactive Claude/Codex clients | no transfer claim |

## Shared-state result

- Before: `main` at `e05178b`, latest tag/release `v0.21.0`, `v0.22.0` absent.
- After: `main`, tag `v0.22.0`, and the release all identify `f5f4556`.
- The generated release commit has sole parent `e05178b` and changes only
  `CHANGELOG.md`.
- The release is published, non-draft, and non-prerelease.
- All eleven public verification checks passed.
- Unexpected delta: none.

## Fail-closed hosted evidence

- Run `33564014091` stopped in analysis and performed no write.
- Run `33565098215` stopped in candidate validation and performed no write.
- Run `33632240778` passed the entire gate and performed the one intended
  publication.

## Evidence locations

- `release/candidate-plan.json` and `release/candidate-evidence.json`: final
  local exact-SHA proof.
- `release/hosted/`: hosted plan, candidate logs/evidence, publication baseline
  and result, and public verification.
- `release/execution-result.json`: mutation result.
- `release/post-write-readback.json`: public readback.
- `release/post-write-comparison.md`: expected-versus-observed comparison.
