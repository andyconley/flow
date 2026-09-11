# Post-release validation

## Release identity

- Work ID: `role-method-differentiation-repair-3`
- Version: `v0.28.0`
- Reviewed production digest T: `4e0a00b81c22d5a7cc2136018188e117893e9ff592813b3ccdb53be400dd8f33`
- Source commit C: `efb73c85d07dc4c091b104f558fa281db0c540ad`
- Release commit R: `6055b6b2dd4ca5fe9a9879d61523bbd08fa0736d`
- R has C as its sole parent. `C..R` contains one release commit and changes only `CHANGELOG.md`.
- Local `main`, `origin/main`, and `v0.28.0^{}` resolve to R.
- Release workflow: <https://github.com/andyconley/flow/actions/runs/34515517662>
- Published release: <https://github.com/andyconley/flow/releases/tag/v0.28.0>

## Installation and generated surfaces

- `~/.flow/source` resolves to `/Users/andyconley/src/flow` at R.
- `flow sync claude --user` and `flow sync codex --user` completed successfully.
- Both corresponding `--check` commands passed.
- An isolated temporary installation regenerated both clients; installed and isolated outputs matched byte for byte.
- Claude test-engineer adapter SHA-256: `95f1c349b92baeea9d1247ff897781529c1851bfbc3d0d78d871b74b2b6a518d`.
- Codex test-engineer adapter SHA-256: `a0b7e8b13b3c0d8e2b237d23d739308eb691eb9958e9d5b7452e0d69b508cbe5`.
- Each test-engineer adapter contains one composed Expertise section and the released method.
- Product-manager and quality-reviewer contain no Expertise section in either client, as required by the accepted scope.
- Claude routing selects `sonnet` at medium effort; Codex routing selects `gpt-5.6-terra` at medium effort.

## Static and diagnostic checks

- `flow runtime smoke --target all --json`: passed with zero failures; four live-client cells remained manual and were exercised below.
- `flow run verify role-method-differentiation-repair-3 --json`: passed.
- `flow doctor`: `ok: true`, zero errors, four accepted warnings.
- `flow doctor --strict`: expected nonzero exit because the same accepted warnings remain; the diagnostic result itself reports `ok: true` and zero errors.
- Accepted warning IDs: `user.claude.runtime_smoke`, `user.codex.runtime_smoke`, `project.adoption.runtime_surfaces`, and `telemetry.plugin_usage`.
- FTS5 was detected as available with Python 3.12.13 and SQLite 3.51.2.

## Fresh Claude checks

- `/flow-status` ran in a new persisted Claude session `b92fc9b4-3ad7-4d4b-930e-fe60cd2f42c9` with observed model `claude-sonnet-5`; it loaded the installed Flow skill and reported `v0.28.0` and the accepted repair-3 state.
- The test-engineer ran in new Claude session `447dfefe-e470-45dc-b195-0c1e6c296c5c` with observed model `claude-sonnet-5`.
- Fixture: an import must reject row 7 where `email` is `not-an-email` and expose an error containing row 7 and email.
- Result: it specified representative invalid input, the required observable error, an integration-level oracle, no persistence of the invalid row, and a successful retry after correction.

## Fresh Codex checks

- `$flow-status` ran in new ephemeral Codex thread `01a08d4e-f021-7780-ac64-39ce9ef2bfb9`; it loaded the installed Flow skill and reported `v0.28.0` and the accepted repair-3 state.
- The test-engineer ran as `/root/postrelease_codex_test_engineer` in thread `01a08d4b-394c-70a0-89a0-ac07fe2cd8f5`; the transcript records model `gpt-5.6-terra`, medium effort, and role `test-engineer`.
- Transcript: `/Users/andyconley/.codex/sessions/2026/09/10/rollout-2026-09-10T17-48-32-01a08d4b-394c-70a0-89a0-ac07fe2cd8f5.jsonl`.
- Transcript SHA-256: `952a416dbd0479511dd1a9dbd5e511385892ce7645a19a93cc83105423469a79`.
- Result: it specified representative row-7 input, an error containing row 7 and email, an integration-level oracle, no persistence, and successful correction and retry.

## Disposition

The reviewed candidate was committed without production drift, fast-forwarded into `main`, released as `v0.28.0`, installed from R, and exercised through fresh Claude and Codex clients. The implementation lane is complete and ready for `flow-archive`.
