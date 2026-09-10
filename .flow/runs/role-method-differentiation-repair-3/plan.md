# Plan: release the evidenced three-role expertise expansion

- Work item: `role-method-differentiation-repair-3`
- Status: Approved 2026-09-10 by Andy Conley
- Definition: approved 2026-09-09 by Andy Conley
- Delivery authorization: continue through commit, merge, semantic release,
  develop-install refresh, and live-client readback after formal review accepts
  the candidate

## Problem statement

The working tree combines three expertise additions that passed their frozen
treatment/control gates with two additions that failed twice. Flow maintainers
and users need the architect, lead-developer, and test-engineer methods without
shipping an unsupported five-role improvement claim. The correction should
move now because its value erodes while the passing work remains coupled to the
failed claim; a third PM/QR experiment has no named workflow need or deadline.

## Desired outcome

Publish a release whose active composed cohort is exactly six roles:
architect, business-analyst, lead-developer, SRE, support-lead, and
test-engineer. Product-manager and quality-reviewer remain usable base agents
with their exact `2712f5f` source bodies and no active expertise composition.
The release preserves every failed historical record byte-for-byte, publishes
a current three-role evidence summary, reaches both installed runtimes, and is
verified through Flow's normal release pipeline.

## Scope

### In scope

- Start from local commit `2712f5f`, including its three commits ahead of the
  current `origin/main`, on branch
  `codex/role-method-differentiation-repair-3`.
- Retain the approved architect, lead-developer, and test-engineer role bodies,
  JSON-LD corpora, competency joins, and behavioral evidence.
- Restore product-manager and quality-reviewer to their exact `2712f5f` base
  bodies; remove their baseline corpus files, composed declarations, and
  vocabulary edges.
- Update the exact-cohort and composition tests, current architecture/layout
  documentation, and the new current release summary at
  `docs/evidence/three-role-expertise-expansion/README.md`.
- Preserve and version the two historical evidence trees and the prior
  `role-method-differentiation` run without altering their bytes.
- Produce run-local receipts, mutation evidence, validation results, handoff,
  and formal review evidence.
- Preserve the existing `.flow/memory/STATE.md` working-tree delta unchanged
  and unstaged. It predates repair-3, is outside acceptance criterion 10, and
  is neither part of this candidate nor release evidence.
- Obtain formal `flow-review` acceptance, commit the accepted source, merge to
  `main`, push, observe all four semantic-release jobs, refresh the develop
  install, and repeat the installed-runtime readback.

### Out of scope

- A third product-manager or quality-reviewer experiment, new candidate method,
  source adoption, or 24-envelope screen.
- A provenance-only admission policy or two-axis evidence-status model.
- Changes to retrieval, archive indexing, ranking, overlays, model routing,
  the JSON-LD format, the shared renderer, or unrelated agents.
- Edits, normalization, rescoring, relabeling, or deletion inside either
  protected evidence tree or the prior run.
- Manual changelog edits, hand-created tags/releases, force pushes, tag
  retargeting, or release deletion.

## States and contracts

This work has no UI state contract. Its required workflow states are:

1. approved plan and validated orchestration;
2. bounded implementation candidate;
3. deterministic and live-client proof complete;
4. implementation handback ready and production digest `T` recorded;
5. formal review accepted;
6. final source `C` committed and merged to `main`;
7. semantic release `R` published and publicly verified;
8. develop install and both native clients read back from `R`.

The following contracts apply throughout:

- **Composition:** parsed set equality must yield exactly the six named roles.
  A count alone cannot pass. Each retained role still renders through the shared
  path in both adapters.
- **Base roles:** PM/QR active Markdown bytes equal `git show
  2712f5f:<path>`. Neither role has a shipped baseline corpus, composed manifest
  flag, active reverse vocabulary edge, or generated Expertise section. User
  overlay files are never deleted.
- **Retained methods:** the six retained role/corpus hashes match
  `evidence/start-receipt.json`; every release-map entry has a valid source,
  locator, forward/reverse join, four extant run records, and a passing gate.
- **Historical evidence:** every path and SHA-256 in
  `evidence/preservation-inventory.json` remains present and identical. The two
  tree digests are recomputed as a secondary check. Aggregate counts never
  replace per-file proof.
- **Current claim:** the active validation surface is fixed to
  `scaffolds/default/flow.toml`,
  `scaffolds/default/expertise/competencies.md`, `docs/architecture.md`,
  `docs/file-structure.md`,
  `docs/evidence/three-role-expertise-expansion/README.md`, and current
  repair-3 plan, validation, handoff, review, and delivery records. Immutable
  historical roots are excluded from current-claim searches and must keep
  their failed five-role language.
- **Release identity:** let `T` be the reviewed production-tree digest and `C`
  the final accepted source commit pushed to `main`. Every production file in
  `C` must match `T`; only declared review/run evidence may be added after
  review. The release workflow analyzes `C`. Semantic-release may create a
  `CHANGELOG.md`-only commit `R`; `C` must be its ancestor, `C..R` must contain
  only `CHANGELOG.md`, and the public tag/release plus refreshed local `main`
  must bind to `R`.
- **Installed clients:** generated configuration is the model/effort authority:
  Claude test-engineer uses `sonnet` at `medium`; Codex test-engineer uses
  `gpt-5.6-terra` at `medium`. Live output must also demonstrate the composed
  oracle method. Parent-session model advice is separate and cannot satisfy
  this check.

## Delivery slices

### Slice 1 — freeze lineage and narrow active composition

1. Fetch remote state without altering the working tree. Create
   `codex/role-method-differentiation-repair-3` at current `2712f5f`; do not
   reset away the three local predecessor commits or the approved working tree.
2. Capture the initial status, remote base, current diff digest, and exact
   mutable-path allowlist. Validate the frozen start receipt, protected
   inventory, and release map before the first production edit, then write a
   separate preimplementation verification record. Never regenerate a frozen
   input to match the current tree. Stop on any mismatch.
3. Restore PM/QR source bodies to `2712f5f`, delete their two active corpus
   files, remove their composed flags and competency terms/edges, and revise
   coverage to 16 terms and 21 entries.
4. Retain the three passing role bodies and corpora byte-for-byte. Update the
   tests to require the exact six-role set, PM/QR inactivity and base-body
   equality, retained joins, and one shared-renderer section for each retained
   role.

Exit: the executable/configuration state is six composed roles, PM/QR are
base-only, the focused suite passes, and every changed production path is on
the allowlist.

### Slice 2 — make the narrowed claim reviewable

1. Update only `docs/architecture.md` and `docs/file-structure.md` for the
   current cohort. Add
   `docs/evidence/three-role-expertise-expansion/README.md` with links and
   hashes for the three passing roles and explicit failed dispositions for
   PM/QR.
2. Preserve the existing `.flow/memory/STATE.md` delta unchanged and unstaged;
   record repair-3 live observations in run-local validation evidence.
3. Add a run-local validation record, change-surface ledger, three restored
   mutation receipts, and
   `.flow/runs/role-method-differentiation-repair-3/evidence/final-receipt.json`.
4. Rehash all protected paths and retained files. Do not edit a historical file
   to make a comparison pass.

Exit: current documentation says three added roles and six composed roles,
historical material remains visibly failed and byte-identical, and the final
receipt reports no unexplained delta.

### Slice 3 — prove the candidate in both runtimes

1. Run the focused composition suite, all three isolated restored mutations, the
   full repository suite, help drift check, whitespace check, both user syncs
   and their checks, runtime smoke, and the two-part doctor gate.
2. Refresh the develop install from this checkout. In fresh Claude and Codex
   sessions, run command discovery and invoke `test-engineer` against the same
   malformed-import fixture. Each record must show client/agent identity,
   configured model and effort, and a concrete oracle naming input, observable
   error, and test level.
3. Inspect actual isolated Claude and Codex generated outputs in addition to
   the shared renderer. Record every check against production-tree digest `T`.
   Any source change invalidates affected proof; rerun rather than carrying
   evidence forward.

Exit: both native clients have conclusive dated records and all candidate gates
pass. Static generation cannot substitute for either live observation.

### Slice 4 — obtain formal acceptance and commit the accepted source

1. Record production-tree digest `T`, its complete changed-path manifest, and
   the validation-receipt digest. Run the `flow-implement` handback, then run
   `flow-review` against the scoped working diff plus the complete
   `origin/main..HEAD` predecessor range.
2. Address findings and rerun affected proof. Review the new `T` again after
   any production change. Merge remains blocked until the review transition
   accepts the exact final production tree.
3. After acceptance, add the review/lifecycle records and commit the complete
   accepted source as `C`. Recommended subject:
   `feat(agents): release three evidence-backed expertise roles`. Use a bounded
   `Release-Note:` trailer that names the three roles and says PM/QR remain base
   roles.
4. Verify every production path in `C` matches `T`; additions after review are
   limited to declared review/run evidence. Record `C`, its parent, tree/diff
   identity, and receipt digest.

Exit: formal review is accepted, final source `C` contains the reviewed
production tree, and no post-review production delta exists.

### Slice 5 — merge, release, and read back

1. Fetch `origin` again. If remote `main` changed, integrate it and repeat the
   affected candidate proof; never force push. Otherwise push the feature
   branch, fast-forward local `main` to `C`, and push `main`.
2. Observe `analyze -> validate-candidate -> publish -> verify-published` for
   source `C`. The workflow's version is authoritative. Require all four jobs
   to pass; do not create or edit release state manually.
3. Verify public release `R`: `C` is an ancestor, `C..R` changes only
   `CHANGELOG.md`, the tag and GitHub release resolve to `R`, and notes state the
   bounded three-role outcome.
4. Fast-forward local `main` to `R`, confirm `~/.flow/source` resolves to this
   checkout, rerun both syncs/checks, runtime smoke, doctor, PM/QR generated-body
   absence checks, and fresh Claude/Codex test-engineer observations.
5. Write final delivery evidence and leave the run ready for archive. Any
   partial or uncertain release follows `docs/release-runbook.md` and repairs
   forward from observed state.

Exit: the remote release, local develop install, generated adapters, and both
native clients all expose the accepted three-role behavior.

## Reversibility and risk

Before merge, the active-surface change is local and reversible through the
feature branch. The public release is the first boundary with costly recovery.
After publication, preserve the tag/release and use a normal corrective commit;
never rewrite public history. A protected-file mismatch, remote concurrency, or
inconclusive live record stops delivery rather than weakening the claim.

No new ADR is needed. The plan applies ADR 0008's existing composition and
role-owned corpus boundary; the two alternative admission policies remain
deferred.

## Recommended lane

Use `flow-implement`. The change spans configuration, role sources, corpora,
tests, current documentation, immutable evidence, two installed runtimes, and
an external release. Its steps are individually reversible until publication,
but the complete proof and handoff require the gated lane.

## Session model advice

- Coordinator recommendation: `judgment`, resolved to `gpt-5.6-sol` at high
  effort for Codex; change recommended because evidence-preservation and
  release mistakes have cross-surface consequences. Availability is unverified.
- Active parent: unknown; Flow received no verified same-session host identity.
- Effective delegated assignments: product-manager -> `gpt-5.6-terra` medium;
  business-analyst -> `gpt-5.6-terra` medium; architect -> `gpt-5.6-sol`
  medium; test-engineer -> `gpt-5.6-terra` medium.
- Switch performed: no.
