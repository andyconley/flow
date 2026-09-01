# Validation Results: Orchestration Safety Contract

## Evidence inventory

- Requirements, acceptance criteria, plan, implementation handoff, and validation plan are in this run directory.
- Current-state research is under `research/`.
- Review evidence is under `review/`: security review (PASS), quality review (APPROVE), and release readiness (manual pre-push gate completed).
- The implementation diff includes the orchestration validator, lifecycle integration, standards/templates, documentation, and focused tests.

## Completed evidence

- Focused orchestration validation and CLI tests: 25 passed.
- `git diff --check`: passed.
- Generated help check: passed.
- Isolated develop-mode install: passed.
- Claude and Codex sync checks: passed.
- `flow doctor`: passed.
- Runtime smoke: passed, with four manual client checks recorded. These checks verify discovery/routing behavior; they do not prove that a runtime granted a capability or that an external provider honored an identity.
- Mutation checks: passed. All five planned weakenings were detected and the implementation was restored after each probe: risk threshold, capability acceptance, overlap detection, verifier independence, and lifecycle refusal-before-write.
- Lifecycle refusal checks confirmed that rejected dispatch, handback, and acceptance attempts leave `run.json` and `events.jsonl` unchanged.
- Security probes covered traversal, evidence-file type, shared-mutation risk, role binding, recovery safeguards, malformed references, and nested controlled values; all refused safely.
- Final stable-tree full test suite: 718 tests passed in 155.111 seconds.
- Final release-staging/import regression: passed; the transitive CLI roster includes `orchestration.py`.
- Isolated release-mode candidate install from the final worktree: passed for setup, both runtime sync checks, `flow doctor --check`, and static runtime smoke. The installer stamped the base tag `v0.20.2`; this is candidate-shape evidence, not proof that the feature exists in the published v0.20.2 artifact.

## Release evidence

- v0.21.0 was published successfully. Release commit `f158595` is on `origin/main`.
- GitHub release: https://github.com/andyconley/flow/releases/tag/v0.21.0; rendered notes are non-empty and `CHANGELOG.md` contains the release entry.
- Fresh v0.21.0 install and v0.20.2 to v0.21.0 update both passed setup, both sync checks, `flow doctor --check`, static runtime smoke, and the expected structured `validate-orchestration` refusal.

## Limitations

The validator checks declarations, paths, referenced regular files, and lifecycle atomicity. It cannot prove external identity ownership, semantic truth of evidence, actual capability grants, or transactional behavior of arbitrary external APIs. Those remain human or adapter responsibilities.

## Archive summary

Implementation, review, validation, publication, and released-artifact verification are complete. The four manual client discovery/model-routing checks remain explicitly unverified limitations.
