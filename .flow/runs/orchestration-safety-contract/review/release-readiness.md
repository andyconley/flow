# Release and Operational Readiness Review

## Scope and evidence inventory

Reviewed the approved plan, validation plan, and acceptance criteria; the current
uncommitted change surface; `release.config.cjs`; `.github/workflows/release.yml`;
`install.sh`, `install-flow.sh`, `cli/lifecycle.py`, and `cli/paths.py`; runtime
diagnostics documentation; and current Git state.

Current release baseline is `origin/main` at `v0.20.2` (`8638255`), with remote
`git@github.com:andyconley/flow.git`. The working branch is
`codex/orchestration-safety`. The worktree is not clean and contains the intended
orchestration changes plus the run overlay; this review did not stage, modify, or
validate a release candidate.

## Reliability Review Summary

### Service Expectations

- A revision-2 release must install a complete CLI capable of importing
  `orchestration.py`, regenerate equivalent Claude and Codex guidance, and reject
  unsafe orchestration transitions without changing `run.json` or `events.jsonl`.
- Existing revision-1 and `legacy/inferred` runs must remain operable under their
  prior gates. This is the central upgrade-compatibility expectation; a new
  protocol revision, rather than a `run.json` schema bump, is the right isolation
  mechanism.
- A published release is not complete until the *tagged artifact* passes install
  or update, `flow doctor`, both-runtime sync, runtime smoke, and an explicit
  `flow run validate-orchestration` exercise in an isolated HOME.

### Observability Gaps

- The proposed validator has the correct local diagnostic shape: phase-aware
  text/JSON findings identify a manifest field, subject, rule, and corrective
  action, while the plan prohibits printing sensitive evidence contents. These
  findings should be retained in `validation-results.md`/the handback alongside
  command, stage, exit code, tag, and commit.
- `flow doctor --json`, sync checks, and runtime smoke diagnose installed and
  generated surfaces, but intentionally cannot prove that a client granted a
  capability or honored provider identity. Release evidence must label those
  manual-runtime limits rather than treating smoke success as capability proof.
- There is no central service telemetry requirement here, which is proportional
  for a local CLI. For shared/external mutations, the required operational signal
  is run-local: a fresh baseline identity/capture time, post-write readback,
  comparison, unexpected-delta disposition, and recovery posture. Do not add
  credentials, raw exports, or secrets to diagnostics.

### Failure Modes

| Failure mode | Existing mitigation | Release acceptance requirement |
| --- | --- | --- |
| New installed CLI omits `cli/orchestration.py` or a transitive sibling | Release staging copies top-level content by blacklist and `_validate_staging` parses the entrypoint and walks imports transitively. | Run the release-staging/import test after the final import graph lands; prove a staged release invokes `validate-orchestration`. |
| Update leaves a half-installed framework | Update stages and validates before atomic replacement. | Exercise both fresh install and update from an earlier release in isolated HOME; preserve the prior install on a deliberate staging failure test. |
| Revision-2 gate writes partial lifecycle state on refusal | Plan requires byte-for-byte unchanged `run.json` and `events.jsonl`; code gates before lifecycle write. | Record before/after hashes for each failing dispatch, handback, and acceptance family. |
| Existing runs become stranded | Revision 1 is retained when absent and `legacy/inferred` stays read-only. | Execute separate revision-1, revision-2, and legacy fixtures from the released artifact. |
| Semantic-release publishes an unusable or undocumented version | The workflow checks that published notes have rendered entries; conventional `feat:` resolves a pre-1.0 minor release. | Confirm tag, release commit on `origin/main`, changelog entry, GitHub release, and non-empty notes. Repair forward if release automation fails after publish. |
| Shared external mutation has stale or insufficient recovery evidence | Contract requires fresh baseline/readback/comparison and recovery state; high-risk needs an independent verifier. | Run one high-risk simulation with a distinct verifier; record any unexercised recovery as a remaining risk, never as proof. |

### Deployment Safety

- **Blocker before publishing:** the only repository workflow found is the
  semantic-release workflow. It runs semantic-release and checks rendered notes,
  but it does not run the Python test suite, release staging, generated-surface
  checks, installer/update checks, `flow doctor`, or runtime smoke before a tag
  can be published. The approved validation plan correctly requires these, but
  they are presently a manual release gate rather than an enforced CI gate.
- Minimum release decision record before pushing `main`: final full test-suite
  result; release-staging/import result; generated Claude/Codex surface
  equivalence result; `git diff --check`; review dispositions; exact source SHA;
  and confirmation that canonical-checkout `docs/backlog.md` is absent. Do not
  publish if any is missing or failing.
- This is a feature release: use at least one conventional `feat:` commit. With
  the current pre-1.0 release rules, that should create the expected minor tag.
  Verify the calculated version before push; no force-push, and fetch immediately
  before integration.
- After publish, use a temporary isolated HOME for both a fresh tagged install
  and an update-path test. Resync both runtimes and compare the installed command
  behavior to the development candidate. A develop-mode install must be updated
  by pulling its canonical clone, not by release-mode replacement.

### Operational Recommendations

1. Treat the missing pre-release CI validation as a release blocker for this
   release. The team may satisfy it with a documented, reviewable manual gate
   now; making it an automated required check is the durable follow-up. The
   post-publish notes check cannot prevent an invalid tagged artifact.
2. Add a concise release-evidence/runbook section to the implementation handback
   before handback: candidate SHA, test commands and exit codes, staging result,
   release workflow URL/status, tag/release/changelog proof, isolated-install
   proof, and repair-forward owner/action if automation fails.
3. Preserve the validator's stated boundary in every support path: it verifies
   declarations and referenced evidence, not hidden runtime permissions,
   semantic correctness, or real external-system behavior. Diagnose a failed
   run from its structured finding and linked evidence artifact; do not infer
   that a passing validator authorized an external mutation.
4. Do not add alerting or telemetry infrastructure for this local CLI solely for
   this feature. The durable audit record and install/runtime diagnostics are
   sufficient at this criticality; the high-risk shared-mutation simulation is
   the proportionate operational readiness test.

## Release readiness verdict

**Not yet ready to publish.** The release model, atomic update path, forward
compatible staging strategy, and planned post-release proof are sound. Readiness
depends on completing the implementation and recording the required validation.
Most importantly, test and installer evidence must be an explicit pre-push gate
because the current release workflow can publish without running them.
