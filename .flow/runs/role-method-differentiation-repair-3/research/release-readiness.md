## Reliability Review Summary

### Service Expectations

- **Observed:** Candidate production digest `T` is
  `4e0a00b81c22d5a7cc2136018188e117893e9ff592813b3ccdb53be400dd8f33`,
  calculated over 29 declared production paths, with PM/QR corpus absence
  represented explicitly. The corrected surface includes the inherited
  `cli/expertise.py` loader and ADR 0008 across the full `origin/main`
  predecessor range, as well as the scoped repair-3 tree. The final receipt
  reports 249 checks and zero failures; the focused suite (49 tests), full
  suite (996 tests), generated help check, diff check, adapter checks,
  runtime smoke, and run verification were recorded against this candidate
  with durable command logs and receipt hashes.
- **Observed:** The current branch is three commits ahead of `origin/main`
  (`2712f5f` versus `090b4df`), and `origin/main` is an ancestor of `HEAD`.
  The delivery path must still fetch immediately before integration: this is a
  point-in-time observation, not permission to assume the remote will remain
  unchanged.
- **Verdict for formal review: ready.** `T` has a bounded, hash-addressed
  production surface and sufficient pre-merge operational proof for formal
  `flow-review`. It is **not ready to merge or release** until that review
  accepts `T` and resolves the strict-doctor-baseline disposition below.

### Observability Gaps

- **Observed:** Static runtime smoke named four manual cells. The two
  command-discovery cells were covered by fresh Claude `/flow-status` and
  Codex `$flow-status` readbacks, and the two role-invocation cells were
  covered by the approved `test-engineer` substitution in fresh Claude and
  Codex sessions. Those invocations showed the configured model/effort and
  the representative row-7/email failure behavior.
- **Plan-specific manual-role substitution: acceptable; not a blocker.** The
  generic static-smoke checklist suggests a low-risk role such as
  `support-lead`; it is not a role-specific release oracle. Repair-3 instead
  explicitly requires `test-engineer` in both native clients, with a concrete
  composed-method fixture, model/effort evidence, and a failure-path response.
  The observed records meet that stronger, change-relevant plan contract.
  Static smoke cannot replace native evidence, but it does not require a
  separate `support-lead` invocation once the approved `test-engineer` matrix
  has been observed. Repeat the same `test-engineer` matrix after `R`.
- **Observed:** The two native agent invocations happened before `T` was
  calculated. They demonstrate the candidate installation, but cannot prove
  the post-release install. Repeating native Claude and Codex agent and
  command readback after `R` is therefore a required delivery proof, not a
  cosmetic confirmation.
- **Observed deviation requiring review disposition:** the approved plan froze
  five strict-doctor warnings; final `flow doctor --json` and strict check
  show four, with `telemetry.claude.harvest` now `ok` after the planned
  refresh. No warning was added or escalated, and doctor has zero errors.
  Operationally, this is acceptable and safer: the refresh converted a stale
  telemetry signal into a fresh one without weakening a product or runtime
  diagnostic. It is not a release-health blocker. The plan's exact-set
  language still means acceptance must record the variance before `T` can
  advance to `C`; this is an evidence-contract blocker, not a request to
  restore a warning.
- **Post-`R` signals to retain:** the workflow URL and all four job outcomes;
  release-plan, candidate-evidence, publication, and published-verification
  artifacts; release/tag/commit identities; the public release URL and notes;
  `flow sync claude --user --check`, `flow sync codex --user --check`, runtime
  smoke, doctor JSON, installed-file hashes/body inspection, and fresh native
  readback transcripts. These provide diagnosis paths for a release that
  publishes correctly but installs or loads incorrectly for users.
- **Observed:** The corrected receipt binds durable logs for the deterministic
  commands, adapter readback, and live capture, and validates the complete
  candidate surface. This improves traceability and makes later diagnosis
  reproducible; it does not change a release gate, the listed blockers, or the
  need to repeat post-`R` user-facing checks.

### Failure Modes

- **Remote movement between review and publication.** The workflow protects
  publication with two `verify-remote-baseline` checks and rejects repeated
  semantic-release analysis drift. Before creating `C`, fetch and rebase or
  merge only after reconciling the current remote range; after push, the
  workflow requires `main` to equal the planned source SHA before publishing.
  If it has moved, stop that run and integrate the new base rather than trying
  to reuse its plan or evidence.
- **Release identity or policy drift.** `release.config.cjs` requires an
  explicit `preview` or `publish` mode and only accepts a canonical GitHub
  HTTPS repository URL for an override. The workflow pins the action and
  semantic-release/plugin versions, and the release-gate policy identity
  covers the pinned policy version map. The expected feature commit convention
  makes a release required; use the prescribed Conventional Commit and keep
  the `Release-Note:` trailer valid. A changed commit message, policy, source
  SHA, previous release, predicted tag, or notes causes the planned analysis
  comparison to fail.
- **Incomplete release workflow.** The four jobs have distinct evidence and
  boundaries: `analyze` creates a credential-free plan; `validate-candidate`
  gates the exact source; `publish` repeats analysis and authorizes one
  publisher run; `verify-published` checks public objects and consumer paths.
  A green publish alone is insufficient. `verify-published` must pass before
  delivery is treated as healthy.
- **Partial publication or failed public verification.** Preserve the tag,
  release, branch state, and retained artifacts. The release runbook directs
  repair-forward with the smallest corrective Conventional Commit; do not
  rerun the publisher blindly, force-push, delete the tag/release, or hand-edit
  generated release state. If branch/tag/release observations disagree or
  inspection is incomplete, escalate to a repository administrator.
- **Develop-install or client-loading regression after `R`.** Pull the release
  commit locally, verify the develop-install source identity, run both user
  sync commands followed by both `--check` commands, then repeat smoke,
  doctor, generated-file inspection, and fresh Claude/Codex readback. A sync
  success without a native readback leaves the user-visible loading path
  unproven.

### Deployment Safety

- **Observed:** The pipeline is serialized (`release` concurrency group with
  no cancellation) and enforces exact plan/evidence digests, source SHA, two
  remote-baseline checks, repeated credential-free analysis, and a
  changelog-only generated release commit whose parent must be the planned
  source commit. This makes the planned `T -> C -> R` chain executable.
- **Required sequence:** accept the hash-addressed `T`; commit final source
  `C` only with production-file hashes matching `T`; fetch and reconcile
  `origin/main`, then integrate and push; observe all four jobs and capture
  their artifacts; identify generated release commit `R`, public tag/release,
  and generated-changelog-only change; pull `R`; then perform the post-release
  develop-install and native-client matrix above.
- **Rollback boundary:** after `R` has published, use repair-forward. Before
  publication, a rejected candidate or analysis drift may be corrected and
  revalidated in a new commit/run. Do not bypass release gates or manually
  repair their state.

### Operational Recommendations

- Treat the four-warning final doctor result as an explicit formal-review
  finding: record why the planned harvest refresh makes the baseline safer and
  whether criterion 8 accepts the improved set. Do not silently substitute it
  for the frozen five-warning oracle.
- At acceptance, retain the reviewed `T` manifest and require the `C`
  production-file comparison before integration. This prevents later review or
  run evidence from changing the accepted behavior.
- After `R`, write a delivery record that names all workflow artifacts, the
  public tag/release and release commit, local/develop-install identities, the
  four-warning doctor result or any new state, and both repeated native
  readbacks. Missing cells remain unverified rather than passing by omission.

### Explicit blockers, nonblocking risks, and verdict

- **Blockers:** formal `flow-review` acceptance of `T`; documented acceptance
  disposition for the five-warning-plan/four-warning-final doctor deviation;
  a `C`-to-`T` production-hash match; and a current-remote reconciliation
  immediately before integration. These block merge/release, not entry into
  formal review. A separate `support-lead` native invocation is not a blocker:
  the plan-specific `test-engineer` native matrix is the applicable oracle.
- **Nonblocking risks:** `origin/main` can advance after this review; retained
  release artifacts expire after 14 days; and the candidate's native evidence
  does not substitute for post-`R` native evidence. The workflow and required
  delivery record provide the corresponding detection/recovery paths.
- **Final verdict:** **ready for formal flow-review; conditionally executable
  for `T -> C -> R`; not ready to merge, publish, or declare deployed until the
  listed blockers and post-`R` proofs are satisfied.**
