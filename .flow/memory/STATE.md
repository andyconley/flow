# Current State

## Active work

- Work item: `release-validation-gate`
- Phase: plan approved
- Goal: prevent semantic-release publication until the exact release candidate passes every deterministic validation check.

## Recently completed

- `orchestration-safety-contract` implemented, reviewed, validated, and released as `v0.21.0`.
- Revision-1 and `legacy/inferred` run compatibility were preserved.
- The unrelated `docs/backlog.md` change in the canonical checkout was not touched.

## Next step

- Run `flow-implement` for `release-validation-gate` from the isolated `codex/release-validation-gate` worktree.
- Before implementation dispatch, replace the planning orchestration manifest with the required high-risk shared-mutation contract.
- Keep live client discovery and model-routing coverage as the separate `runtime-smoke-cannot-exercise-client-discovery` follow-up.
