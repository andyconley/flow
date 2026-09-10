# Validation plan: three-role expertise expansion

- Work item: `role-method-differentiation-repair-3`
- Status: Approved 2026-09-10 by Andy Conley
- Primary oracle: exact active state plus per-file evidence, not aggregate
  counts or prose assertions

## Baseline and scope proof

Before production edits, save the current HEAD, `origin/main`, branch, complete
status, tracked diff digest, and mutable-path allowlist under this run. Use a
run-local Python validator to validate every frozen hash in:

- `evidence/start-receipt.json`
- `evidence/preservation-inventory.json`
- `evidence/release-evidence-map.json`

The validator must report each path and mismatch in a separate
`evidence/preimplementation-verification.json`; it must not rewrite any frozen
input. Recompute both historical tree digests using the receipt's documented
sorted-path/NUL/file-hash/newline algorithm. Missing, renamed, or mismatched
input blocks implementation.

The final change-surface check classifies every changed path. Production paths
must fall within acceptance criterion 10. Preserve the pre-existing
`.flow/memory/STATE.md` delta unchanged and unstaged. Protected historical
paths and the prior run may be newly versioned, but their bytes cannot change.

## Deterministic checks

Extend `tests/test_expertise_composition.py` so it directly proves:

- parsed set equality for the six named composed roles;
- retained body/corpus SHA-256 values and exact three-role evidence-map
  membership;
- schema, audience, globally unique role-prefixed IDs, source/locator fields,
  and forward/reverse competency joins for architect, lead-developer, and
  test-engineer;
- exact `2712f5f` base-body bytes for PM/QR and absence of their baseline
  corpora, composed flags, active vocabulary edges, and rendered Expertise
  sections;
- exactly one shared-renderer Expertise section in both adapters for each
  retained role;
- current documentation's three-role/six-role claim on the fixed active surface.

Run:

```text
/opt/homebrew/bin/python3.12 -m unittest tests.test_expertise_composition
/opt/homebrew/bin/python3.12 -m unittest discover -s tests
/opt/homebrew/bin/python3.12 scripts/regenerate-flow-help.py --check
git diff --check
flow sync claude --user
flow sync codex --user
flow sync claude --user --check
flow sync codex --user --check
flow runtime smoke --target all --json
flow doctor --json
flow run verify role-method-differentiation-repair-3
```

Record command, start/end time, exit status, source/tree identity, and log path.
Repeat focused checks after affected edits. Run the full suite once against the
final candidate and again only if later source changes warrant it.

## Restored mutation checks

Run mutations separately against a disposable copy, save their receipts, and
restore exact original bytes before the passing focused run.

1. Reintroduce PM composition by adding its composed declaration or active
   corpus/edge. The cohort or inactive-surface guard must fail and identify PM.
2. Remove test-engineer composition, its corpus, or its release-map record. The
   retained-role guard must fail and identify test-engineer.
3. Negate a retained lead-developer positive obligation while preserving the
   words used by the former substring assertion, for example by inserting
   `Do not` before `first classify reversibility`. The exact approved-body or
   normalized full-obligation guard must fail. This check is mandatory.

Each receipt contains target path, original and mutated SHA-256, command,
expected nonzero exit, diagnostic excerpt, restored SHA-256, and successful
post-restoration focused result. A mutation that passes or cannot be restored
blocks review.

## Evidence and current-claim checks

Create `evidence/final-receipt.json` from the frozen start inputs. It must name
all 112 protected files, both historical tree digests, and the six retained
body/corpus hashes, with zero unexplained differences.

Validate `release-evidence-map.json` for exactly architect, lead-developer, and
test-engineer. Each record must have `gate_result: pass`, matching body/corpus
hashes, source locators, entry IDs, one result hash, and four extant run-record
hashes. Reject duplicates, PM/QR membership, aggregate-only proof, or a stale
path.

Search only the active surface fixed in `plan.md`. Require the new summary,
current docs, validation, and handoff to say three newly composed roles and six
total. Reject an active five-role-success or eight-role-composed claim. Do not
search/alter immutable historical roots to make this check pass.

## Native-client checks

Use the same fixture in fresh Claude and Codex sessions:

> An import must reject `row 7, email="not-an-email"` and expose an error that
> contains `row 7` and `email`. Define the minimum test oracle.

The response must name that representative input, the observable error, the
integration test level, and the relevant failure path. The agent must be
`test-engineer`, with this composed method visible in the installed body:
`Define a test oracle with a concrete example`.

| Client | Configured model | Effort | Required record |
| --- | --- | --- | --- |
| Claude | `sonnet` | `medium` | client/agent identity, installed-source identity, actual isolated generated-output hash/method, visible model/effort evidence, fixture, response, observer, timestamp |
| Codex | `gpt-5.6-terra` | `medium` | client/agent identity, installed-source identity, actual isolated generated-output hash/method, visible model/effort evidence, fixture, response, observer, timestamp |

Also run `/flow-status` in Claude and `$flow-status` in Codex to close the
existing command-discovery checklist. Record each client result as `observed`,
`unavailable`, or `inconclusive`; only `observed` passes. Generated text or
static smoke cannot replace a native invocation.

Run this matrix twice: once against reviewed production-tree digest `T` before
formal review and once after release with local `main` at `R`. A production
change between a check and review invalidates that check.

## Doctor posture on the current host

Run `flow doctor --json` and require exit 0, `ok: true`, `errors: 0`, and all
source/install/scaffold/config/sync/agent-policy/overlay/FTS5 diagnostics needed
by this release to remain `ok`.

Also run `flow doctor --check --json`. On the current host its expected exit is
1 because the captured baseline has exactly these warning ids:

- `user.claude.runtime_smoke`
- `user.codex.runtime_smoke`
- `project.adoption.runtime_surfaces`
- `telemetry.claude.harvest`
- `telemetry.plugin_usage`

Require the same five-warning set, no errors, no higher severity, and no lost
required `ok` diagnostic. Any new or unexplained warning fails local
validation. The isolated hosted `validate-candidate` doctor check remains an
independent hard release gate.

## Formal review and delivery proof

Formal review maps acceptance criteria 1-10 to the final receipt, mutation
records, repository logs, active-surface search, and both `T` live-client
records. Merge and the final source commit are blocked until `accept-review`
succeeds.

After acceptance, record:

- reviewed production-tree digest `T`, final source commit `C`, its parent and
  subject, and a comparison proving every production path in `C` matches `T`
  while any post-review additions are limited to declared review/run evidence;
- feature-branch and `origin/main` readback proving `C` is merged unchanged;
- the Release workflow URL and all four successful job results;
- analyzed source `C`, predicted version/tag, release-plan and evidence digests;
- generated release commit `R`, with `C` as ancestor and `C..R` limited to
  `CHANGELOG.md`;
- remote tag and GitHub release resolving to `R`, plus release notes that name
  the three-role outcome without implying PM/QR passed;
- local `main` fast-forwarded to `R`, `~/.flow/source` resolving to this
  checkout, passing post-release sync/check/smoke/doctor output, generated
  PM/QR absence, and both repeated native-client records.

If remote state changed before merge, integrate and revalidate. If publication
is partial or uncertain, preserve workflow artifacts and follow
`docs/release-runbook.md`; do not force, retag, delete, or blindly retry.

## Pass condition

The release passes only when all ten acceptance criteria, all three mutation
checks, both candidate native-client records, formal review, the
`T -> C -> R` identity chain, all four release jobs, public readback,
develop-install refresh, and both post-release native-client records are
observed. Unknown and unavailable are not passes.
