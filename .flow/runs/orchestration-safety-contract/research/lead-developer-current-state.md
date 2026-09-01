# Lead Developer Current-State and Execution Sequence

## Scope and basis

This analysis maps the approved orchestration-safety requirements to the
current Flow source tree at `origin/main` / `v0.20.2`. It does not change
product files. The only in-worktree changes presently visible are the run's
untracked `.flow/` artifacts.

The plan's **Explicit exclusions** section appears internally inconsistent: it
lists many files that the earlier **Existing sources to update** and **CLI and
tests to update** sections explicitly require (including `cli/runstate.py`,
`cli/flow.py`, `tests/test_flow.py`, `README.md`, and CLI/architecture docs).
Treat the bulleted exclusions that follow that list as authoritative, and
resolve the accidental file-list conflict before implementation commits are
prepared. The execution below follows the approved change lists and excludes
only the clearly stated non-goals and the canonical checkout's unrelated
`docs/backlog.md` edit.

## Current implementation seams

### Lifecycle and CLI

- `cli/runstate.py` is the single owner of C-lite state. `SCHEMA_VERSION` is
  `1`; `apply_transition()` constructs a copied payload, checks only static
  artifact/disposition presence, then writes `run.json` and appends
  `events.jsonl`. This is the correct hook point for revision-2 gate checks,
  provided all validation runs before `_write_run()` and `_append_event()`.
- `cli/flow.py` intentionally owns parser declaration and dispatch only. The
  new `run validate-orchestration` parser, import, and dispatch should remain
  there; validation and printing logic belong in the new module.
- `tests/test_flow.py` already has a C-lite lifecycle cluster near lines
  350-510 and uses a subprocess CLI harness plus direct module loading. Put
  command-level integration/atomicity coverage beside that cluster, and add a
  dedicated validator test class rather than scattering fixtures through
  unrelated command tests.
- `cli/fsutil.py` already supplies repository-root and atomic-write helpers.
  Reuse repository-root resolution, but do not let the validator rely on the
  lifecycle writer: it must be read-only and callable independently.

### Framework source and generated surfaces

- `scaffolds/default/flow.toml` is the source manifest for both runtime
  adapters. Command prose under `scaffolds/default/commands/` is generated to
  both Claude and Codex surfaces, so the canonical commands must stay
  runtime-neutral; do not edit installed generated skills.
- `scripts/regenerate-flow-help.py` derives `flow-help` content from the
  scaffold/manifest. It should first be run in check mode; update generated
  help only if the command catalog/help assertions actually change.
- `scaffolds/default/standards/collaboration.md` and `evidence.md` contain the
  closest existing rules. The new standard should own detailed requirements,
  while these standards link to it for role outcomes/evidence provenance; this
  avoids a second divergent specification.
- `scaffolds/default/templates/run-template.md` is deliberately light. Add
  orchestration-manifest linkage, rather than embedding full duplicated
  schemas in this template.

### Documentation and release

- `docs/adr/` does not exist on the current branch. The ADR slice must create
  the directory and establish the project naming/index convention explicitly
  (or add the first self-contained ADR without assuming an index).
- `docs/cli-reference.md`, `docs/file-structure.md`, `docs/architecture.md`,
  `docs/runtime-adapters.md`, and `README.md` currently describe C-lite as a
  two-file projection. Update them consistently to explain the separate
  run-local manifest and revision-gated enforcement.
- `release.config.cjs` produces a pre-1.0 minor for `feat:` commits. At least
  one feature commit is required; changelog/release commit remains automation
  owned and must not be hand-created.

## File-level delivery sequence

### Slice 1 — contract source, templates, and ADR

1. Add `scaffolds/default/standards/orchestration.md` as the sole normative
   contract. Define artifact ownership, controlled enums, claim status,
   risk calculation, capability-state semantics, scope overlap limitations,
   shared-state baseline/readback/recovery, reconciliation, verification
   independence, and the validator's declared-structure boundary.
2. Add these authoring templates:
   - `scaffolds/default/templates/agent-brief.md`
   - `scaffolds/default/templates/orchestration-manifest.md`
   - `scaffolds/default/templates/findings-reconciliation.md`
   - `scaffolds/default/templates/external-mutation-record.md`
3. Create `docs/adr/` and add one ADR documenting why detailed orchestration
   state is run-local and versioned while `run.json` remains schema-1 lifecycle
   projection.
4. Modify `scaffolds/default/standards/collaboration.md`,
   `scaffolds/default/standards/evidence.md`,
   `scaffolds/default/templates/implementation-handoff.md`, and
   `scaffolds/default/templates/run-template.md` to reference—not restate—the
   new contract.
5. Add only concise trigger/link text to the applicable canonical commands:
   `flow-define.md`, `flow-solution.md`, `flow-plan.md`, `flow-implement.md`,
   `flow-review.md`, and `flow-scout.md`.

Safe boundary: this makes the intended contract reviewable before parser and
lifecycle behavior changes. It also establishes exact field names that tests
and code will consume.

### Slice 2 — independent manifest validator and direct command

1. Add `cli/orchestration.py`. Export a small pure/read-only interface:
   manifest loading; repository-relative safe-path normalization; structural
   schema/type checks; enum checks; deterministic risk calculation; declared
   scope overlap detection; stage validators; and diagnostic rendering.
2. Treat parsing findings as structured records (for example field path,
   subject id, rule, corrective action) and derive both stable human text and
   `--json` output from those records. Never include baseline contents in a
   diagnostic.
3. Modify `cli/flow.py` to import only a `cmd_validate` entry point, declare
   `flow run validate-orchestration WORK_ID --stage dispatch|handback|acceptance
   [--json]`, and dispatch it beside existing run commands.
4. Extend `tests/test_flow.py` with direct validator tests and CLI formatting/
   exit-code tests. Fixtures should cover positive single, delegated read-only,
   disjoint concurrent, serialized shared mutation, and high-risk external
   mutation manifests; use fixture builders to keep negative cases isolated.

Safe boundary: no lifecycle behavior changes yet; consumers can author and
validate manifests explicitly, which exposes contract-design gaps without
stranding existing runs.

### Slice 3 — revision-gated lifecycle enforcement

1. Modify `cli/runstate.py` to add a protocol revision constant/default for
   newly created C-lite runs while retaining `SCHEMA_VERSION == 1`.
2. Add a small revision resolver: absent `protocol_revision` means revision 1;
   no mutation may add revision 2 to an existing revision-1 run. Keep
   `legacy/inferred` read-only behavior unchanged.
3. Before lifecycle writes, merge candidate artifacts/dispositions into an
   in-memory candidate payload, resolve the `orchestration_manifest` path, and
   invoke the validator for revision-2 gates:
   `approve-definition`, `approve-solution`, `approve-plan` -> dispatch;
   `mark-handback-ready` -> handback; `accept-review` -> acceptance.
4. Only after validation passes should `apply_transition()` write the run
   projection or append its event. Preserve the existing behavior that a
   refused transition returns the old payload; do not create a run directory
   on a failed initial transition.
5. Extend the existing lifecycle test cluster with revision-1 compatibility,
   legacy compatibility, successful revision-2 full path, each gated refusal,
   and byte-for-byte `run.json`/`events.jsonl` assertions for every failing
   family.
6. Extend the `archive-scout` path only if its invocation declares delegation
   or shared external mutation. This should be an explicit, opt-in parameter
   or artifact signal, not a blanket manifest requirement for ordinary scouts.

Safe boundary: behavior changes are isolated to revision 2. Existing active
runs keep their previous lifecycle contract and can still be verified.

### Slice 4 — integration documentation and generated-surface proof

1. Update `README.md`, `docs/architecture.md`, `docs/file-structure.md`, and
   `docs/cli-reference.md` with the new command, file model, revision rules,
   and structural-validation limits. Update `docs/runtime-adapters.md` only
   where it needs to state that canonical command guidance syncs identically.
2. Update command source text with dispatch timing (immediately before agent
   spawn or shared mutation), claim/reconciliation expectations, and stage
   gates. Keep semantic tiers in `flow.toml`, not in command prose.
3. Run `python3 scripts/regenerate-flow-help.py --check`; regenerate only if
   output is stale. Sync both user adapters from source and run their drift
   checks/runtime smoke; generated files are validation output, not source
   edits unless the repository intentionally tracks a generated help file.
4. Add/update source-level tests that assert relevant command references
   without overfitting every paragraph of documentation.

### Slice 5 — review, release, and installed-artifact verification

1. Run focused validator/runstate tests, then the full suite, help check,
   adapter sync checks, runtime smoke, release-staging/import checks, and
   `git diff --check`. Record each command/result in the run validation
   artifact; state mutation-test evidence or the exact uncovered behavior.
2. Have independent review assess the final high-risk fixture and evidence
   collector/verifier separation; record findings plus dispositions in the
   reconciliation and handback artifacts.
3. Make logical Conventional Commit slices after reading
   `scaffolds/default/standards/git-commits.md` and its cited vendor spec.
   Suggested order: `feat(orchestration): add manifest validation`; then
   `feat(run): gate revision-two lifecycle`; then `docs(orchestration): ...`
   if docs are not co-committed with their corresponding behavior. Do not
   commit generated local installs or unrelated overlay state.
4. Immediately before integration, fetch `origin/main`, confirm the worktree
   branch can fast-forward/rebase cleanly, inspect `git remote -v` and staged
   paths, then push without force. Verify semantic-release's tag, GitHub
   release, changelog, and rendered release notes.
5. From the released tag, perform isolated installation/update plus both
   runtime sync and smoke checks. Record commands/output snippets in release
   evidence before declaring the release complete.

## Integration hazards and decisions to settle before coding

- **Plan contradiction:** resolve the “Explicit exclusions” file list before
  staging; otherwise an implementer could reasonably omit mandatory CLI/tests
  or alter files the plan claims excluded.
- **Manifest discovery:** the plan says revision-2 approvals require a
  persisted `orchestration_manifest` artifact. Decide whether the manifest is
  required at `start-definition` for every new run, supplied at the first
  approval, or only required when the run's mode/risk triggers enforcement.
  The stated “Each enforced run” and “new runs fail closed where required”
  language favors adding it at `approve-definition`; implementation should
  document that an ordinary new revision-2 run is still enforced, not silently
  treated as revision 1.
- **Revision compatibility:** defaulting every newly-created run to revision 2
  means an initial `start-definition` can stay manifest-free, but subsequent
  approval gates cannot. `verify()` must accept both revisions while still
  rejecting unknown/non-integer revision values where appropriate.
- **Atomicity:** `_write_run()` and `_append_event()` are sequential. The new
  validation must occur before either; otherwise a failed validator could
  leave partial state. This initiative does not solve a filesystem failure
  between successful writes, so do not overclaim transactionality.
- **Path model:** paths in a manifest must be checked relative to repository
  root after normalization, including symlink considerations. Simple
  `Path.is_relative_to()` after `resolve()` can accidentally require target
  existence or traverse symlinks; define the desired lexical-versus-realpath
  policy and test `..`, absolute paths, and symlink escape behavior.
- **Scope model:** ancestor/descendant overlap is straightforward for repo
  paths. External scopes cannot prove coordinate aliasing, so static pass must
  be explicitly declaration-level and force serialization/owner review for
  ambiguous same-target regions.
- **Gate artifact timing:** a transition can introduce the manifest artifact
  in the same command. Validation must use the candidate merged artifact map,
  not the old persisted map, while failure must retain the old files exactly.
- **High-risk independence:** compare stable producer/evidence-collector/
  verifier identities, not display role names. A high-risk run needs a
  verifier distinct from both producer and evidence collector; standard-risk
  runs record identities but do not require separation.
- **Capabilities:** only `confirmed` satisfies a required dispatch capability;
  `unknown` must produce a targeted failure rather than a generic mismatch.
  The CLI must not imply it queried runtime grants.
- **Shared mutation:** “fresh” must have a deterministic machine-checkable
  representation if the CLI is to validate it. If freshness is inherently
  provider-specific, validate required timestamp/source identity presence and
  label temporal sufficiency as human review rather than inventing a TTL.
- **Fixture sensitivity:** external baseline and execution artifacts in tests
  must contain only synthetic/redacted data; diagnostics should identify paths
  and rules, never echo artifact contents.
- **Release behavior:** semantic-release evaluates commit history on `main`.
  A feature commit is needed for the requested minor bump; release verification
  is external CI state, so no publication claim is valid until tag/release
  assets are observed.

## Recommended verification matrix

| Area | Focused proof |
| --- | --- |
| Validator | Schema/types/enums, risk boundaries, capability states, safe paths, scopes, each stage's positive and negative fixtures, text/JSON parity |
| Lifecycle | Revision-1 and legacy preservation; revision-2 success; each failing gate leaves both lifecycle files byte-identical |
| Shared mutation | Disjoint additive concurrency allowed; same-target structural serialized; missing baseline/recovery/readback/comparison/disposition refused |
| High risk | Every hard trigger; 0/1/2 aggravators; conflicting stored class; verifier conflicts; standard-risk verifier allowed |
| Runtime/docs | Help regeneration check; Claude/Codex sync check; runtime smoke; command-source references agree with standard |
| Release | Full suite, release staging/import, diff check, clean staged-path audit, remote/tag/GitHub release/changelog/notes, released-tag install smoke |

## Handoff recommendation

Start implementation with Slice 1 and freeze field names/template examples in
review. Then build Slice 2 as a standalone validator before changing
`runstate.py`. This preserves a narrow fault boundary: validator defects are
debugged as read-only checks before they can block lifecycle progress.
