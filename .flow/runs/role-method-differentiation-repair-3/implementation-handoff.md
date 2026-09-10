# Implementation handoff: three-role expertise expansion

- Work item: `role-method-differentiation-repair-3`
- Status: Approved for implementation 2026-09-10 by Andy Conley
- Approved definition: `requirements.md` and `acceptance-criteria.md`
- Implementation plan: `plan.md`
- Validation contract: `validation-plan.md`

## Start state

- Local `main` is at `2712f5f`, three commits ahead of the currently observed
  `origin/main` at `090b4df`.
- The working tree contains the uncommitted five-role candidate plus two
  immutable evidence trees. Do not reset or clean it.
- `evidence/start-receipt.json`, `evidence/preservation-inventory.json`, and
  `evidence/release-evidence-map.json` freeze the inputs for repair-3.
- Definition approval and `start-plan` are recorded in `run.json`.
- Delivery through commit, merge, release, install refresh, and live readback is
  authorized. Formal review acceptance remains a hard precondition for merge.

## File disposition

| Owner | Files | Action |
| --- | --- | --- |
| Integration | `scaffolds/default/flow.toml`, `scaffolds/default/expertise/competencies.md` | Narrow to the exact six-role cohort and 16-term/21-entry vocabulary. |
| Role source | `scaffolds/default/agents/product-manager.md`, `scaffolds/default/agents/quality-reviewer.md` | Restore exact `2712f5f` bytes. |
| Role source | `scaffolds/default/agents/lead-developer.md` | Retain exact frozen bytes. Architect/test-engineer role files are unchanged but hash-checked. |
| Corpus | architect, lead-developer, and test-engineer JSON-LD files | Retain and version exact frozen bytes. |
| Corpus | product-manager and quality-reviewer JSON-LD files | Delete from active baseline; never delete user overlay files. |
| Tests | `tests/test_expertise_composition.py` | Exact cohort, retained joins/hashes/rendering, inactive PM/QR, current claims, and mutation-sensitive guards. |
| Current docs | `docs/architecture.md`, `docs/file-structure.md` | Three added roles; six composed total. |
| Release evidence | `docs/evidence/three-role-expertise-expansion/README.md` | New current summary outside protected roots. |
| Historical evidence | both existing `docs/evidence/...` roots and `.flow/runs/role-method-differentiation/` | Version unchanged; verify each frozen hash. |
| Run evidence | `.flow/runs/role-method-differentiation-repair-3/` | Planning, receipts, mutation records, validation, handback, review, and delivery evidence. Use `git add -f` because the local exclude hides new run files. |
| Pre-existing unrelated delta | `.flow/memory/STATE.md` | Preserve unchanged and unstaged; exclude it from the repair-3 candidate and evidence chain. |
| Installed outputs | user Claude/Codex generated files | Regenerate only with Flow sync; never hand-edit or commit them. |

The implementer owns shared production edits serially. Validation agents may
write only their run-local reports. No protected path is a writable surface.

## Build order

1. Validate orchestration, fetch remote read-only state, create
   `codex/role-method-differentiation-repair-3`, capture the allowlist, and
   validate all frozen inputs without rewriting them, then save a separate
   preimplementation verification.
2. Restore/remove PM/QR active surfaces before editing tests or current claims.
3. Narrow manifest/vocabulary and strengthen composition tests while retaining
   the three passing sources exactly.
4. Update current docs, add the new summary, and write final/mutation receipts;
   leave `.flow/memory/STATE.md` untouched.
5. Run the complete local, isolated-adapter, doctor, and `T` live-client matrix
   from `validation-plan.md`.
6. Mark implementation handback ready and run formal review against production
   tree `T`, the scoped working diff, and `origin/main..HEAD`. Fix findings and
   repeat affected proof.
7. After acceptance, commit final source `C`, prove its production files match
   `T`, then fetch, fast-forward merge, and push.
8. Observe and verify semantic-release commit `R`, pull it to local `main`,
   refresh the develop install, repeat sync/static/live readback, and write the
   delivery record.

## Commit and release contract

Recommended feature commit:

```text
feat(agents): release three evidence-backed expertise roles

Release-Note: Flow now gives architect, lead-developer, and test-engineer source-backed methods while product-manager and quality-reviewer remain on their base roles.
```

Commit only after formal review accepts `T`, so the feature commit can include
the accepted review/lifecycle artifacts. The production-file manifest must
prove that adding those records did not change the reviewed behavior. The
workflow determines the version.

## Guardrails

- Use `2712f5f` active source files as the PM/QR restoration authority, not
  experiment control bodies.
- Do not edit any path listed by `preservation-inventory.json`; force-adding an
  unchanged file is allowed, changing its bytes is not.
- Do not loosen an oracle, remove a failed record, or search historical text as
  a current claim to make the release pass.
- Do not delete or rewrite user-owned overlay corpora.
- Do not change the renderer, loader, schema, routing, retrieval, or release
  workflow in this work item.
- Do not merge before `flow-review` accepts. Do not bypass or manually repair a
  release gate; use the runbook and repair forward.

## Required handback

The implementation handback must contain:

- changed-path classification and exact retained/removed/restored role list;
- start/final receipt comparison and three-role evidence-map result;
- focused/full/help/diff/sync/smoke/doctor logs;
- three independent restored mutation records, including semantic negation;
- active-current-claim search result;
- candidate Claude and Codex command/agent live records;
- reviewed production-tree digest `T`, final source commit `C`, and full
  remote-base review range;
- formal review verdict and dispositions;
- `T -> C -> R` review/merge/release evidence, workflow URL, public tag/release URL,
  release notes, and generated-changelog-only comparison;
- post-release install identity, generated body inspection, and repeated Claude
  and Codex live records;
- every deviation, unknown, or unavailable observation. No missing cell becomes
  a pass by omission.

No architecture decision is open. Another engineer can execute this handoff
without the original conversation.
