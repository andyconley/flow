# Plan: proof for the three-role expertise release

- Owner role: test-engineer
- Date: 2026-09-09
- Scope: validation only. This plan preserves the approved six-role cohort and
  does not authorize a PM/QR candidate trial or any protected-evidence edit.

## Question

What evidence detects an incorrect narrowing, an incomplete generated delivery,
or a release that reaches source control but not the installed native clients?

## Evidence basis

- The start receipt fixes the source revision, six retained role/corpus hashes,
  two aggregate historical-tree digests, and the hash of the protected
  inventory and release-evidence map.
- `preservation-inventory.json` expands preservation to every protected
  historical file, including the complete prior definition/review run.
- `release-evidence-map.json` names architect, lead-developer, and
  test-engineer, each passing gate, their source/role/corpus hashes, and four
  primary/counter records. Repair-2 remains a failed PM/QR record.
- The prior test audit shows why literal presence tests and static smoke are
  insufficient by themselves: semantic negation can survive a substring test,
  and static runtime checks do not prove native-client loading.

## Deterministic proof

Run these after all planned production changes on reviewed production tree `T`
and before formal review. Save command, exit status, tree identity, and output
path in the validation record. A nonzero result, a missing record, or a result
against another tree stops review.

| Oracle | Required result | Wrong result it rejects |
| --- | --- | --- |
| Cohort set | Parse `scaffolds/default/flow.toml`; `generation_mode = "composed"` is exactly `{architect, business-analyst, lead-developer, sre, support-lead, test-engineer}`. | Seven/eight roles, missing retained role, or a renamed PM/QR composition declaration. |
| Retained sources and joins | For architect, lead-developer, and test-engineer: current role-body and corpus SHA-256 match `start-receipt.json`; JSON-LD schema, source/locator, audience, unique ids, and forward/reverse competency joins pass. | A quiet edit, removed source locator, stale vocabulary edge, or wrong corpus returned by the loader. |
| PM/QR base-role readback | Product-manager and quality-reviewer body bytes equal their frozen pre-repair control hashes; loader selects no active corpus; vocabulary has no active `Taught by` edge; shared renderer emits zero expertise sections; each remains addressable as a base agent. | A remaining repair-2 instruction, orphaned active corpus, a stale generated section, or deletion of the agent instead of restoration. |
| Generated adapters | In isolated Claude and Codex generation outputs, run each adapter generation/check and inspect the actual emitted test-engineer body: exactly one Expertise section containing `Define a test oracle with a concrete example`; inspect each emitted PM/QR body: zero Expertise sections. Keep the shared-renderer unit test too. | A shared renderer result assumed to prove both adapters, source-only correctness that never reaches a generated surface, or a stale PM/QR section. |
| Named behavioral evidence | Validate `release-evidence-map.json` as JSON and require exactly the three approved role names, `gate_result: pass`, matching start hashes, entry ids/locators, result-record hashes, and four extant primary/counter record hashes for each. | Aggregate `3/3` prose, an accidentally cited PM/QR record, a stale hash, a duplicate role, or an unproven retained role. |
| Historical preservation | Rehash every exact path in `preservation-inventory.json`; require all paths exist and every SHA-256 matches. Separately recompute both sorted-path/NUL/file-hash tree digests with the receipt's stated algorithm and require the recorded counts and digests. | Removed/reformatted historical response, review, source-verification record, or README; a final receipt created after an unrecorded baseline change. |
| Current claim and scope readback | Search only the predeclared current-document surface and new repair-3 artifacts; require the six-role/three-role statement and reject a current five-role-success/eight-role-composed claim. Exclude the immutable inventory paths. Compare final changed production paths to the declared acceptance-criterion-10 surface. | A current overclaim hidden in a release note, or retrieval/routing/overlay/renderer/unrelated-role work bundled as narrowing. |

The focused command is `/opt/homebrew/bin/python3.12 -m unittest
tests.test_expertise_composition`; the final suite is
`/opt/homebrew/bin/python3.12 -m unittest discover -s tests`. Also require
`git diff --check`, `flow sync claude --user --check`, `flow sync codex --user
--check`, and `flow runtime smoke --target all --json`. The local doctor
contract has two parts: `flow doctor --json` must exit 0 with `ok: true`,
`errors: 0`, and all required install/sync/drift/policy/overlay/FTS5 diagnostics
`ok`; `flow doctor --check --json` must exit 1 with exactly these five warnings
and no error/higher severity/new warning: `user.claude.runtime_smoke`,
`user.codex.runtime_smoke`, `project.adoption.runtime_surfaces`,
`telemetry.claude.harvest`, and `telemetry.plugin_usage`. Repeat that comparison
after the released install. The hosted `validate-candidate` doctor check remains
an independent hard gate and must pass. The implementation plan may add a
dedicated receipt validator, but its output is additional evidence only; direct
rehashing of the inventory remains the preservation oracle.

## Restored mutation proof

Mutate a disposable copy or make each edit in the working tree, run the named
focused guard, record its expected nonzero status and diagnostic, restore the
exact original bytes, then rerun the full focused suite. Never retain mutation
bytes or alter protected evidence.

1. **PM/QR exclusion mutation:** re-add `generation_mode = "composed"` for
   product-manager (or add one active PM/QR corpus entry/competency edge).
   The exact-cohort/inactive-surface guard must fail because the observed set
   is no longer six or because PM/QR renders Expertise. Restore the source and
   require the focused suite to pass.
2. **Retained-role mutation:** remove test-engineer from the composed
   declaration, remove its required corpus, or change its evidence-map record
   to a failing/missing value. The retained-cohort/evidence-map guard must
   fail and name test-engineer. Restore and require the focused suite to pass.
3. **Mandatory retained-obligation semantic mutation:** negate the retained
   test-engineer positive obligation while preserving the words already searched
   by the guard (for example, retain `representative input`, `expected
   observable result`, and `test level` while making the instruction prohibit
   that behavior). The semantic guard must fail, proving it evaluates the
   obligation rather than substring presence. Restore the exact retained body
   and require the focused suite to pass. `Not applicable` is not permitted.

Each mutation receipt records target path, original and mutation SHA-256,
command, exit status, failure excerpt, restoration SHA-256, and the successful
post-restoration focused-suite result. Any mutation that passes, cannot be
restored byte-for-byte, or has no recorded failure blocks acceptance.

## Native live-client proof: `test-engineer`

### Pre-review observations on T

At reviewed production tree `T`, refresh the active develop install from `T`,
run both user syncs and their `--check` forms, and then observe both clients.
These two records are required before formal implementation review. The observed
agent must be `test-engineer`, using the composed method **Define a test oracle
with a concrete example**. Expected configured runtime settings from the
working tier are:

| Client | Expected configured model | Expected effort | Required observable result |
| --- | --- | --- | --- |
| Claude | `sonnet` / resolved `claude-sonnet-5` | `medium` | A fresh native Claude session invokes `test-engineer`; visible agent/session metadata shows the configured model and effort, and the response to the fixture names a representative malformed import row, its user-visible error containing row number and field name, and an integration-level oracle. |
| Codex | `gpt-5.6-terra` | `medium` | A fresh native Codex session invokes `test-engineer`; visible task/agent metadata shows that model and effort, and the same fixture response supplies the same behavior-level oracle. |

Use the same small fixture in both clients: an import must reject
`row 7, email="not-an-email"` and expose an error containing `row 7` and
`email`; the answer must name that input, observable result, and integration
test level. This checks the rendered method through a behavior that generic
framework listing cannot satisfy. Retain a dated transcript/permalink or
screenshot showing (1) client identity, (2) agent identity, (3) model and
effort, (4) the fixture, and (5) the returned oracle. Generated-file text,
static smoke, or a parent-session model label does not satisfy this gate.

For each T-client record use `observed`, `unavailable`, or
`inconclusive`. Only `observed` with every item above passes. A client that
cannot start, cannot invoke the named agent, hides model/effort, loads a stale
agent, or gives a response missing the concrete oracle is a hard stop; record
it and do not call tree `T` review-ready.

### Post-release installed observations

After the public release, repeat the same two fresh-client observations against
the refreshed develop install at generated release commit `R`. These records
prove installed delivery and must identify `R`; they do not replace the
pre-review records at `T`. An unavailable or inconclusive post-release record
blocks the release handoff even when the earlier candidate check passed.

## Commit, merge, release, install, and readback proof

The following sequence binds the final behavior to the public release rather
than to an uncommitted working tree.

1. **Review T:** record reviewed production tree identity `T`, its validation
   receipt digest, and the two pre-review client records tied to `T`. Formal
   review evaluates this completed production tree. Stop on an unexplained
   production path, preservation mismatch, or failed T client observation.
2. **Accepted source commit C:** after formal acceptance, create the
   Conventional Commit `C`. Record its SHA, subject, parent SHA, and acceptance
   records. Require `T` to be an ancestor of `C` and require `git diff
   --name-only T..C` to contain only declared review/run/operational artifacts;
   any production path in that range invalidates the T review and requires
   renewed validation and formal review.
3. **Merge C:** after the PR or main merge, record its URL, merge SHA, and
   `origin/main` SHA after `git fetch origin`; require
   `git merge-base --is-ancestor C origin/main` to succeed. A local commit,
   open PR, or remote branch that does not contain `C` is not merge proof.
4. **Semantic release from C to R:** retain the release workflow URL and its
   preview, validated plan, publication result, and reconciliation artifacts.
   The workflow analysis must identify `C` as its source SHA and a
   release-required version transition. Semantic-release then creates generated
   CHANGELOG-only release commit `R`: require `C` to be an ancestor of `R`, and
   require `git diff --name-only C..R` to contain only `CHANGELOG.md`.
   Preview/plan drift, a failed publish, a no-release result, a non-ancestor
   `C`, or any other path in `C..R` stops the release path.
5. **Remote tag and GitHub release at R:** record the predicted tag/version,
   then verify `git ls-remote --tags origin refs/tags/<tag>` and the peeled tag
   object resolve to `R`. Record the GitHub release URL/identifier and verify
   its tag and target SHA equal `R` and the workflow publication artifact. A
   local tag, a tag at `C` or another commit, or a release page with another
   target fails this proof.
6. **Develop-install refresh and final readback at R:** fast-forward the
   develop checkout to verified `origin/main` at `R`; verify `~/.flow/source`
   resolves to that checkout and `git rev-parse HEAD` equals `R`. Run
   Claude/Codex user sync and checks, static smoke, and doctor again. Reinspect
   generated test-engineer and PM/QR bodies and run the two post-release native
   client observations. Record the installed source SHA `R`, generated-file
   readback, check outputs, and installed client records in the final validation
   result.

Publication is complete only when formal review evaluates `T`, `T..C` contains
only declared review/run/operational records, the workflow analyzes `C`, `C` is
an ancestor of changelog-only `R`, and the remote tag target, GitHub release
target, develop-install HEAD, generated adapters, and both post-release native
client records identify `R`. The separate pre-review deterministic and native
client records remain bound to `T`. Any divergence stops the release record for
forward repair; do not retag, force-push, delete a release, or rerun selected
evidence to obtain a better result.

## Stop conditions and handoff artifacts

| Stop condition | Required artifact / disposition |
| --- | --- |
| Wrong cohort, PM/QR active surface, invalid join/render, or mismatched evidence map | Failed focused test or validator output; fix source, rerun the complete deterministic set. |
| Historical inventory/tree mismatch | Final receipt listing every mismatch; preserve both states and investigate. No acceptance or release claim. |
| Mutation fails to fail or restoration differs | Mutation receipt and current hashes; correct the guard before acceptance. |
| Static validation or local doctor-contract failure | Command log tied to tree `T`; correct and rerun the affected gate plus full suite. |
| T or post-release Claude/Codex observation unavailable/inconclusive | Dated client record stating the missing observable; formal review or release handoff, respectively, remains blocked. |
| T/C/R/merge/tag/install identity disagreement, `T..C` production delta, or `C..R` more than `CHANGELOG.md` | Workflow/reconciliation record and remote state; repair forward from observed state without destructive history changes. |

The final validation handoff should contain the start and final receipts,
preservation comparison, evidence-map validation, focused/full logs, two
mutation receipts, adapter/smoke/doctor logs, active-document/scope report,
two pre-review client records at `T`, formal-review evidence, T-to-C
review/run-delta evidence, commit/merge evidence, release workflow and remote
tag/release evidence at `R`, two post-release installed-client records at `R`,
and post-install readback. These artifacts prove the three-role release without
reopening PM/QR behavioral evaluation.
