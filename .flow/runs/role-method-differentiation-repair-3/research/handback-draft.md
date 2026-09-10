# Implementation handback draft: three-role expertise expansion

- Work item: `role-method-differentiation-repair-3`
- Handoff state: ready for formal `flow-review`
- Candidate production tree `T`: `4e0a00b81c22d5a7cc2136018188e117893e9ff592813b3ccdb53be400dd8f` (the final receipt records the full SHA-256 ending `dd8f33`).
- Reviewed production surface: 29 declared paths, including the complete inherited `origin/main..HEAD` release range (`origin/main` `090b4df` through `HEAD` `2712f5f`) and the scoped repair-3 working-tree paths. The inherited `cli/expertise.py` and ADR 0008 changes are included in `T`.

## Scope and role behavior

The active composed cohort is exactly six roles: architect, business-analyst,
lead-developer, SRE, support-lead, and test-engineer. Repair-3 adds and retains
source-backed behavior for architect, lead-developer, and test-engineer. Their
role instructions, JSON-LD corpora, source locators, competency joins,
composition declarations, shared-renderer output, and passing evidence remain
hash-valid.

Product-manager and quality-reviewer were restored to their exact frozen
`2712f5f` base bodies. Their repair-2 methods, active baseline corpora,
composition declarations, vocabulary edges, and generated Expertise sections
were removed. User overlays were preserved. Both repair-2 generations remain
historical failed evidence; neither role is represented as passing. The two
prior evidence trees and the prior run remain byte-identical across all 112
protected files.

## Evidence and validation

The final receipt reports 250 checks with zero failures, including the protected
per-file inventory, retained-role hashes, active-state checks, complete
candidate surface, command-log hashes, and live captures. The focused suite
passes 49 tests; the full suite passes 996 tests. Durable evidence covers the
focused/full test commands, help and diff checks, user and isolated Claude/Codex
sync checks, static runtime smoke, normal and strict doctor output, run
verification, three restored mutation tests, and current-claim search.

The three negative mutations were independently applied and restored: PM
composition reintroduction, removal of the test-engineer declaration, and
negation of the lead-developer positive obligation while retaining prior
vocabulary. Each named guard failed on mutation and the original bytes and
focused suite were restored before `T` was calculated.

Fresh candidate records show test-engineer loading through Claude and Codex
with the configured method and model/effort, plus the command readback in both
clients. Claude used `sonnet`/`medium`; Codex used `gpt-5.6-terra`/`medium`.
The generic support-lead smoke prompts were intentionally superseded by this
approved, change-relevant test-engineer matrix; no support-lead result is
claimed.

## Operational disposition required in formal review

`flow doctor --json` passes with zero errors and four warnings. Strict doctor
returns the expected nonzero status with the same four warnings. The approved
plan froze five warnings; `telemetry.claude.harvest` became `ok` after the
planned refresh. No warning was added or escalated, and release-relevant
checks remain `ok`. SRE and implementation-quality review accept the state
operationally, but formal review must explicitly disposition this exact-set
variance before `T` advances to `C`.

The pre-existing `.flow/memory/STATE.md` working-tree delta is excluded from
the candidate and release evidence, remains byte-identical to its captured
start hash, and must stay unstaged. It is not a repair-3 production change.

## Review and delivery boundary

No source commit exists yet. The approved `T → formal review → C` contract
requires review acceptance before creating `C`; merge, semantic-release `R`,
develop-install refresh, and repeated native-client readback remain downstream
work. After acceptance, `C` must reproduce every production hash in `T`, then
the remote range must be reconciled before integration. Publication requires
the four workflow jobs, public tag/release verification, changelog-only `R`
comparison, and fresh Claude/Codex installed-client records.

## Roles engaged

The orchestration engaged solution-architect, business-analyst,
product-manager, test-engineer, lead-developer, quality-reviewer, sre,
tech-writer, and explorer lanes. Formal review should retain the quality,
testability, and SRE evidence already recorded and judge `T` against the
approved requirements, plan, acceptance criteria, and findings reconciliation.
