# Planning architecture: three-role expertise expansion

- Work item: `role-method-differentiation-repair-3`
- Owner role: architect
- Date: 2026-09-09 (America/New_York)
- Recommendation: one reversible narrowing change followed by formal review,
  branch merge, the existing semantic-release workflow, and installed-runtime
  readback

## Architecture Summary

### Context

The current tree is based on `2712f5f` and contains an uncommitted five-role
expertise expansion. Only architect, lead-developer, and test-engineer have the
frozen evidence required for this release. Product-manager and
quality-reviewer remain valid base agents, but their proposed methods failed
the treatment-over-control gate. The smallest coherent change removes those
two methods from active composition without altering the composition engine,
JSON-LD format, role ownership, adapters, or either historical evidence root.

The tree is currently on local `main` at `2712f5f`, three commits ahead of
`origin/main`; `feat/expertise-join-validation` points at the same commit. The
implementation branch must therefore start at the current `2712f5f` lineage,
not reset to the remote base. Review and merge must inspect the complete
`origin/main..candidate` range so the already accepted join-validation commits
remain visible.

### Proposed Shape

- Keep expertise composition as the existing manifest-driven path:
  `flow.toml` selects a role, `expertise/<role>.jsonld` supplies role-owned
  entries, `competencies.md` supplies the reverse vocabulary join, and the
  shared renderer generates both runtime bodies.
- Narrow only the active membership and its claims. The final composed set is
  exactly `architect`, `business-analyst`, `lead-developer`, `sre`,
  `support-lead`, and `test-engineer`.
- Restore product-manager and quality-reviewer from their exact source bytes at
  commit `2712f5f`. Their historical control/treatment bodies are evidence,
  not restoration sources, and must not be copied into the active scaffold.
- Keep all protected historical files byte-identical. The authoritative path
  list and hashes are
  `evidence/preservation-inventory.json`; the retained source hashes are in
  `evidence/start-receipt.json` and `evidence/release-evidence-map.json`.
- Add the current release explanation at
  `docs/evidence/three-role-expertise-expansion/README.md`. It points to the
  immutable results and says that PM/QR failed; it does not copy, rewrite, or
  relabel historical evidence.
- Add the after-change digest at
  `.flow/runs/role-method-differentiation-repair-3/evidence/final-receipt.json`.
  This is outside every protected root and compares the same complete path set
  plus the six retained role/corpus files captured at the start.
- Reconcile installed Claude and Codex agents only through the normal user sync
  commands. Generated user files are deployment outputs, not new repository
  sources.

### Change Surface

| Disposition | Surface | Required change |
|---|---|---|
| Retain exactly | `scaffolds/default/agents/architect.md`, `scaffolds/default/agents/lead-developer.md`, `scaffolds/default/agents/test-engineer.md` | Preserve the hashes in the start receipt. The lead-developer short/full-plan contract is part of the retained change. |
| Retain exactly | `scaffolds/default/expertise/architect.jsonld`, `scaffolds/default/expertise/lead-developer.jsonld`, `scaffolds/default/expertise/test-engineer.jsonld` | Preserve entry ids, sources, locators, behavior, and hashes in the release evidence map. |
| Restore | `scaffolds/default/agents/product-manager.md`, `scaffolds/default/agents/quality-reviewer.md` | Remove only the uncommitted repair instructions, then require byte equality with `git show 2712f5f:<path>`. |
| Remove | `scaffolds/default/expertise/product-manager.jsonld`, `scaffolds/default/expertise/quality-reviewer.jsonld` | Delete these active, untracked corpora. Historical designs and run records remain untouched. |
| Narrow | `scaffolds/default/flow.toml` | Retain composed declarations for architect, lead-developer, and test-engineer; remove them for PM/QR; leave the three existing composed roles unchanged. |
| Narrow | `scaffolds/default/expertise/competencies.md` | Retain the architect, test-engineer, and two lead-developer terms; remove the PM/QR terms and rows; update the coverage prose to 16 terms, 21 entries, and exactly six composed roles without changing shared join behavior. |
| Narrow and strengthen | `tests/test_expertise_composition.py` | Make the exact set six; retain schema/join/renderer assertions for the three additions; assert PM/QR match the `2712f5f` base and have no active corpus, manifest declaration, vocabulary edge, or rendered expertise section. Put exclusion and retention mutations in isolated temporary copies. |
| Reconcile | `docs/architecture.md`, `docs/file-structure.md` | State three newly composed roles and six total, while preserving per-role corpus ownership and the existing renderer boundary. |
| Add | `docs/evidence/three-role-expertise-expansion/README.md` | Current release summary with exact cohort, three passing evidence links, two failed-role dispositions, and no five-role improvement claim. |
| Add/update | `.flow/runs/role-method-differentiation-repair-3/` | Plan, validation, handoff, validation results, final receipt, review, archive, and delivery evidence. These may change because this run is not protected by its own preservation inventory. |
| Generate externally | user Claude and Codex adapter files | Refresh from the accepted source with `flow sync claude --user` and `flow sync codex --user`; verify with both `--check` forms. Do not hand-edit installed files. |

No CLI, renderer, corpus schema, ADR, release workflow, retrieval, model-routing,
overlay, or persistence module changes belong in the candidate. The existing
`.flow/memory/STATE.md` modification is an unrelated pre-implementation delta:
record its starting hash, leave its bytes untouched, keep it unstaged, and
exclude it from C. Any other changed path outside the table is a blocking scope
exception until it is explained and accepted.

### Execution and Release Sequence

1. **Preserve the current lineage and boundary.** Create
   `codex/role-method-differentiation-repair-3` at current `2712f5f` without cleaning
   or resetting the working tree. Freeze the mutable-path allowlist. Validate
   the frozen start receipt, preservation inventory, and release map before the
   first production edit, then write a separate preimplementation verification
   receipt; a mismatch stops work.
2. **Subtract PM/QR before changing claims.** Restore the two role bodies to
   exact `2712f5f` bytes, delete their two active corpora, remove their manifest
   declarations and competency edges, and prove that the composition loader
   produces base bodies for both. This prevents docs or tests from describing
   a state the runtime does not yet have.
3. **Retain and prove the passing cohort.** Keep the architect,
   lead-developer, and test-engineer sources hash-identical; update the exact
   cohort tests and both isolated mutations. Re-run forward/reverse join and
   shared-renderer checks before documentation work.
4. **Reconcile current claims and receipts.** Update the two current
   architecture/layout documents, add the new release summary outside protected
   roots, then produce the final receipt by comparing every protected path and
   all retained source hashes to the frozen inputs. Confirm the unrelated
   `.flow/memory/STATE.md` delta retains its recorded starting hash and remains
   unstaged.
5. **Validate reviewed production tree T.** Run focused and full tests,
   `git diff --check`, both adapter generation checks, static runtime smoke, and
   doctor. Refresh the active develop install, then record dated live
   test-engineer loads in Claude and Codex with the expected method and
   configured model/effort. Capture the completed production tree as **T**.
   Either missing live record blocks review acceptance and publication.
6. **Review T and commit final source C.** Run `flow-review` against T and the
   full `origin/main` comparison so the three predecessor commits remain
   visible. Address findings and repeat affected checks. After acceptance, add
   only the resulting run records, confirm the production projection is still
   T, and commit the final accepted source as **C** with a Conventional Commit
   and accurate bounded `Release-Note:` trailer. Explicitly stage candidate
   paths so `.flow/memory/STATE.md` remains unstaged and outside C.
7. **Merge only after formal acceptance.** Push the feature branch, merge C to
   `main` without rewriting or omitting the three local predecessor commits,
   and read back `origin/main` at C. Do not manually edit `CHANGELOG.md`, create
   a tag, or create a GitHub release.
8. **Release through the existing four-job gate.** Let the `main` push run
   `analyze -> validate-candidate -> publish -> verify-published`. Call the
   final accepted source commit **C**. Semantic-release analyzes C and may
   create a generated **R** whose only source-tree delta from C is
   `CHANGELOG.md`. Treat the workflow's analyzed version as authoritative
   rather than predicting a version in the plan. Require all four jobs to pass
   and verify that C is an ancestor of R, `C..R` changes only `CHANGELOG.md`,
   and the public tag and GitHub release bind to R. Also verify notes, fresh
   install, and upgrade from the prior release.
9. **Refresh and read back locally.** Fast-forward local `main` to R, confirm
   `origin/main` and the public tag also identify R and C remains its required
   source ancestor, retain the active `~/.flow/source` link, run both user syncs
   and checks, static runtime smoke, and doctor again. Record the remote,
   public, installed, and live-client results before archiving the run.

Steps 6-9 implement the engineer's explicit request to commit, merge, and
release. They remain downstream of formal implementation review, which
preserves the approved definition's prohibition on pre-review publication.

### Risks and Tradeoffs

- **Historical evidence drift:** broad search/replace or documentation cleanup
  could touch a protected README or prior run. Use the frozen allowlist and
  per-file receipt, never a directory count alone. Any mismatch blocks the
  release; do not normalize or regenerate the affected historical file.
- **False restoration:** the repair-2 evidence control bodies are generated
  experiment artifacts and are not guaranteed to be source-identical. Restore
  PM/QR from `2712f5f` and compare bytes directly.
- **Retained behavior drift:** deleting vocabulary blocks or narrowing tests can
  accidentally remove an architect/lead/test join. Hash the role/corpus sources
  and run both forward and reverse joins before and after the edit.
- **Stale installed expertise:** source correctness does not remove an old
  expertise section from an already generated user agent. The normal sync,
  check, and live-client readback are required deployment proof.
- **Release overclaim:** semantic-release notes derived from a broad feature
  message could imply five roles improved. The commit subject, optional
  highlight, summary, and public notes must all say three newly composed roles
  and must keep PM/QR failures explicit.
- **Lineage ambiguity:** local `main` is ahead of `origin/main`. Branch from the
  current source and review the whole remote-base range; resetting to remote or
  squashing away required predecessor commits risks losing already accepted
  work or obscuring what is being released.

### Rollback and Recovery

- Before merge, abandon or reset only the feature branch after preserving the
  run evidence; `main` and the public release remain unchanged.
- After merge but before publication, revert the accepted feature commit on
  `main`, push the revert, and re-run both syncs. Do not edit the remote branch
  history.
- After a public release, do not delete or retarget the public tag, generated
  changelog commit, or release. Repair forward with a normal `fix`/`revert`
  commit and let the same gated workflow publish the correction. Consumers who
  must recover immediately install the prior public release and run both user
  syncs.
- If publication is partial or uncertain, preserve the workflow artifacts and
  remote observations, follow `docs/release-runbook.md`, and read before any
  retry. Never treat a local successful sync as proof that the public release
  succeeded.
- A protected-file mismatch is an evidence incident, not a routine Git revert.
  Stop, retain both observations, and identify the exact writer before deciding
  whether restoration is safe.

### ADR Recommendation

- Needed: no
- Reason: this change applies the already approved ADR 0008 composition and
  role-owned JSON-LD boundaries while narrowing run-local membership. The
  viable alternatives were retaining all five despite failed evidence,
  reverting all five and discarding three supported additions, or introducing
  a two-axis admission policy. The first violates the accepted gate, the second
  delays proven value, and the third is explicitly deferred. Revisit an ADR
  only if Flow later permits provenance-only active methods or changes the
  durable admission/status contract.

## Draft plan recheck

- Reviewed: `plan.md`, `validation-plan.md`, and
  `implementation-handoff.md`
- Verdict: structurally sound after three required reconciliations and one
  proof clarification

### Required: validate the frozen start artifacts; do not regenerate them

The earlier draft directed refreshing the start receipt, protected inventory,
and release map before production edits. The other two drafts correctly say
to validate the hashes recorded in those artifacts. Rewriting the artifacts now would
move their capture time and could replace the original tracked-diff identity
after definition and planning records have changed. A receipt called “start”
must continue to describe the boundary already captured before repair-3
production mutation.

Keep these three inputs byte-identical:

- `evidence/start-receipt.json`
- `evidence/preservation-inventory.json`
- `evidence/release-evidence-map.json`

At implementation entry, read them and write a separate run-local
`evidence/preimplementation-verification.json` containing the observed hashes,
per-path comparison, current branch/HEAD/remote identities, and result. Stop on
any mismatch. The final receipt then compares against the original frozen
inputs, preserving a meaningful before/after chain.

### Required: use the reviewed-tree to source to release identity chain

The agreed release shape uses reviewed production tree **T**, final accepted
source commit **C**, and semantic-release's optional `CHANGELOG.md`-only commit
**R**. Keep those three identities explicit from review through installed
readback.

Use one final source identity:

1. Capture completed production tree T and its proof, leaving the unrelated
   `.flow/memory/STATE.md` modification outside the candidate and unstaged.
2. Formal review evaluates T. Append the acceptance-only run records, confirm
   the production projection remains T, and commit the final accepted source as
   C. The delta from the reviewed snapshot to C is limited to declared run
   records; `.flow/memory/STATE.md` is not versioned by this candidate.
3. Merge and push C. Semantic-release analyzes C.
4. If semantic-release creates **R**, require C as its ancestor and require
   `C..R` to change only `CHANGELOG.md`. The public tag/release, `origin/main`,
   and refreshed local `main` bind to R.

This is the complete durable identity contract: T -> C -> R.

### Required: make doctor a two-part gate on this known-warning host

`flow doctor --check --json` currently exits 1 by design because five
warning-grade diagnostics are present, while the same payload reports
`"ok": true` and `"errors": 0`. The five observed warnings are the two manual
runtime-smoke notices, one project adoption decision, stale Claude telemetry,
and the plugin-usage snapshot. Calling this command a passing “strict doctor”
gate is impossible on the present host and would conflate expected support
notices with a product regression.

Do not drop doctor and do not accept an arbitrary nonzero result. Use both
checks:

1. Run `flow doctor --json`; require exit 0, `ok: true`, `errors: 0`, and the
   required source, scaffold, config, launcher, develop-install, Claude/Codex
   sync, drift, agent-policy, project overlay/manifest, and FTS5 diagnostics to
   remain `ok`.
2. Run `flow doctor --check --json`; require its documented exit 1 and compare
   its structured warning set with the captured five-warning baseline. Fail on
   any error, any new warning id, a higher severity, a missing required `ok`
   diagnostic, or an unexplained baseline change. The candidate release
   workflow's isolated doctor check remains an independent hard gate and must
   still pass in `validate-candidate`.

Repeat the same structured comparison after the released install. This keeps
strict warning visibility and the hosted release gate intact without requiring
the implementation to repair unrelated telemetry/adoption state.

### Clarify: prove both generated adapters through their actual outputs

The drafts say `tests/test_expertise_composition.py` proves one Expertise
section “in both adapters.” A direct `sync.agent_body` assertion proves the
shared renderer only once; it does not independently prove Claude and Codex
generated surfaces. Keep that shared-renderer unit assertion, then use isolated
Claude and Codex sync outputs or the existing adapter checks to assert that
each generated test-engineer body has exactly one retained method and each
generated PM/QR body has none. The live-client records remain the final adapter
consumption proof.

### Confirmed structural fit

- File dispositions are complete and coherent: six active composed roles, 16
  competency terms, 21 entries, PM/QR restored from `2712f5f`, two active
  PM/QR corpora deleted, and architect/lead/test sources retained exactly.
- The new current summary and final receipt are outside the protected roots;
  all 112 protected files remain governed by per-file hashes.
- The branch name `codex/role-method-differentiation-repair-3`, remote-change
  handling, no-force policy, formal review before merge, semantic-release-only
  publication, installed readback, and repair-forward recovery fit the current
  repository architecture.
- The rollback boundary is correct: branch-level recovery before merge,
  ordinary revert before publication, and forward repair without rewriting a
  public tag or release after publication.
