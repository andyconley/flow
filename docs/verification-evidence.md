# Verification evidence and bounded repairs

New OpenHands workflows record `verification_revision=1`. Existing workflows stay
inspectable and retain their recorded contract; status labels them
`historical_unbound`. Start a new approved workflow to adopt this contract. Do not
edit a run's revision, approval seals, evaluation baseline or repair projection.
The creation/approval/repair journal is checked against those projections.

Flow still owns lifecycle approvals and durable artifacts. OpenHands still owns
execution, delegation and conversation persistence. This feature runs approved
verification commands and validates evidence at lifecycle boundaries; it does
not replace the SDK agent loop, retry machinery or permission system.

## Before plan approval

The host Delivery Lead uses the existing `agent-brief.md`: name inputs and their
versions, specialist, scope, prohibited changes, output path and success
conditions. Reconcile specialist evidence in the existing plan, handoff and
validation plan. Add `.flow/runs/<work-id>/verification-plan.json`:

```json
{
  "schema_version": 1,
  "repair_limit": 2,
  "evaluation_inputs": ["tests/test_behavior.py", "tests/fixtures/input.json"],
  "checks": [
    {
      "id": "behavior",
      "criterion": "AC-1 in acceptance-criteria.md",
      "argv": ["python3", "-m", "unittest", "tests.test_behavior"]
    }
  ]
}
```

Register all material tests, fixtures, simulator/evaluator code and test
configuration. Registration uses explicit regular files, not globs. An input's
bytes and executable mode are captured at plan approval, including ignored files.
The registered file list and check argv are sealed as part of the plan. Review
whether the inventory and checks actually prove the criteria before approval.
Missing coverage is a review judgment, not something file hashes establish.

## Record actual verification

After `flow workflow execute` returns, the host uses the approved check ID:

```sh
flow workflow check <work-id> --check-id behavior \
  --session-id <actual-producer-session> --assignment-id <brief-id> \
  --environment '<Python/tool versions and relevant environment>' --timeout 1800
```

The command executes the approved argv directly, without shell interpretation,
streams stdout/stderr into a unique run log and appends a result to
`verification.json`. It records exit status, command, session/assignment identity,
environment, timestamps, elapsed time, registered-input identities and the tested
workspace fingerprint. Put any generated outputs in `.flow/runs/<work-id>/`.
A timeout terminates the verification process group and records a failed result.
A check that changes workspace inputs cannot count as passed.

Before launching the command, Flow durably records an incomplete invocation.
If the runner dies before storing its result, the next session must allocate a
new targeted repair instead of reusing the previous allocation. The lost result's
exit code, final log hash and elapsed time remain unknown. An incomplete result
never satisfies an acceptance check; only a later completed, current passing
result can do so. The host must ensure a lost runner has stopped before retrying.
Total check elapsed time stays unknown when a result was lost; the observed
partial duration is labeled separately.

The SDK execute holds the existing run lock. An SDK specialist must not invoke
Flow evidence or lifecycle commands from inside that execution. It runs ordinary
tests through its tools and returns the technical handback; the host records the
checks after the SDK returns. The evidence/check/repair commands fail promptly
when the run is busy, rather than waiting on their parent. `verification.json`
is created only by the host after execution. Specialists must not create, edit,
or synthesize this record or captured logs. They link the expected record from
their handback and report host verification as pending until it exists.

The fingerprint includes HEAD, tracked bytes (including deleted paths), executable
modes and nonignored untracked files. Git metadata and `.flow/runs/` are excluded.
Ignored dependencies/environment are not a hermetic snapshot: register material
ignored evaluator inputs and describe remaining environment dependencies. Git
project roots are required; submodules and symlinks require separate verification
and are rejected rather than silently traversed.

Reference `verification.json` in `implementation-evidence.md` and `handback.md`.
Entering review and accepting review require all approved checks to pass on the
current fingerprint, with matching logs and approval digests. Changed source,
untracked input, registered test or HEAD makes old results stale. Re-run all
checks for the changed fingerprint. The evidence is sealed by the existing
handback gate. Review reports and SDK state live in the excluded run directory.
Archived evidence describes the accepted version; it does not claim that a later
workspace still matches that version.

## Test changes and success conditions

Changing a registered evaluator input requires explicit independent review before
handback. Record before/after failure and success evidence in a run file:

```sh
flow workflow review-test-change <work-id> --reviewer quality-reviewer \
  --reviewer-session-id <separate-review-session> --disposition equivalent \
  --rationale '<why the exact approved behavior is still proved>' \
  --evidence .flow/runs/<work-id>/test-repair-proof.md
```

A legitimate repair corrects a broken import, erroneous fixture or harness
nondeterminism while preserving the approved behavior, coverage and thresholds.
Review includes the actual diff, before/after logs and replacement proof. The
record binds the precise approved/current input hashes; another change invalidates
that review. The reviewer session must differ from every recorded producer.

Deleting assertions, lowering thresholds, skipping required coverage, replacing a
required integration with a stub, or changing simulation semantics is a material
criterion change. Stop and seek separate user approval in a successor workflow
linked to the old one. An uncertain equivalence also escalates. The review command
rejects `material` and `uncertain`; it cannot grant that approval. Do not describe
such a change as an equivalent test repair.

This is an operator/reviewer contract, not authentication: an agent with the same
OS access can forge identities or rewrite both state and history. Independent
review and an external frozen evaluator remain necessary to detect dishonest
attestations, incomplete inventories, or implementation shortcuts that pass the
registered tests. No new identity or sandbox system is claimed.

## Targeted repair and escalation

A failed check cannot simply be rerun in a new session. Allocate its repair:

```sh
flow workflow repair <work-id> --check-id behavior --specialist lead-developer \
  --scope '<fix only this failure>' --reason '<failed check and diagnosis>' \
  --failure-evidence .flow/runs/<work-id>/failure-proof.md
```

This uses `request-refinement`, retains approved criteria and planning seals,
releases only implementation/review evidence, and records the narrowed assignment
and failure-evidence hash in existing lifecycle history. It also works during
implementation. There are two repair allocations per approved check for the
whole workflow. Pause/resume, new sessions and model changes do not reset them.
Each allocation follows a distinct check result; one cannot allocate repeatedly
without running the check. A third allocation is rejected; after an exhausted
failed check the workflow is blocked for user escalation. SDK/network request
retries remain SDK behavior, not new Flow repair allocations. This does not
intercept arbitrary checks run directly through agent tools.

## Reporting

`flow workflow evidence-report <work-id> --json` reports checks, failures, gate and
handoff rejections, repairs, test-change reviews, check duration, workflow lifecycle
span and the session/work identities used by existing usage reporting. Rejected
verification gates are annotations in existing history, not lifecycle advances.
For already harvested usage, optionally pass `--usage-store <existing.db>`; it is
opened read-only and existing deduplicated SDK estimates are joined by work ID.
Those sums are labeled `observed_sdk_estimated_cost`; they do not assert complete
whole-workflow coverage. Total `sdk_estimated_cost` remains unknown without that
coverage, even when every imported row has a positive estimate.
Missing/partial estimates, aggregate tokens, actual bills and human review time
remain null. An SDK estimate is not a native subscription bill. The lifecycle
span is not a live end-to-end experiment timer. Do not equate summed concurrent
session time with wall time, or gate rejections with measured model rework gains.
See `docs/verification-evaluation.md` for the frozen comparison protocol.

Lifecycle publication recovery: verification workflows retain the current committed event in `run.json` with a unique event identity. History reads include that event if journal publication was interrupted; the next transition materializes it before replacing the pending event. Journal publication uses atomic replacement. Recovery preserves approved input baselines and spent repair allocations, without deduplicating separate transitions or rejections. This covers process interruption and write errors, not authenticated protection against the same OS user or a claim of power-loss durability.

## Incomplete independent review outputs

For verification-v1 work, `workflow execute --stage review` can inspect an
implementing workspace before handback to review an equivalent test repair. It
leaves lifecycle approval with the host. The specialist writes `review.md` with
exactly one `Verdict: ACCEPT` or `Verdict: REJECT`. When registered test inputs
changed, it also writes `Test equivalence: EQUIVALENT`, `MATERIAL` or `UNCERTAIN`,
with before/after rationale. Implementation correctness and test equivalence are
separate questions: correcting addition logic fulfills an addition criterion;
fixing an import preserves that criterion only if the assertions are retained.
An equivalent test repair can accompany a rejected implementation.

SDK completion without a newly produced usable artifact is `incomplete_review`
and a nonzero CLI exit. Chat-only ACCEPT and repetitive output do not supply a
receipt. Execution records the review ID, artifact digest, tested workspace and
approved artifact bindings; the existing `review-test-change` command still
requires a separate host action and actual independent session identity. Material
or uncertain changes cannot use that command for approval. Semantic equivalence
remains an independent review judgment; a matching hash is not semantic proof.

For an incomplete output, the host can allocate a targeted retry:

```sh
flow workflow repair WORK --check-id review-output --specialist quality-reviewer \
  --scope 'Produce the missing independent review; preserve approved criteria' \
  --reason 'Incomplete review output' \
  --failure-evidence .flow/runs/WORK/review-outcomes/REVIEW_ID.json
```

Then execute review again, optionally with `--new-session`. The existing
`repair_attempts` journal and two-allocation limit apply under the reserved
`review-output` check identity. Resume, new sessions and ordinary implementation
repairs do not refund these allocations. Review repairs stay in the current lane;
they do not reopen approved implementation artifacts. Exhaustion blocks and
requires escalation. Waiting-for-confirmation continuations reuse the attempt.

A shared 1800-second review deadline starts with the first review dispatch and
persists across confirmation, repair and new sessions. The pinned SDK `arun()` /
`interrupt()` API receives the remaining deadline; late output is never accepted.
This does not establish that remote provider compute or external tool processes
have stopped. Full-workflow elapsed time and arbitrary external compute are not
controlled by this deadline. Original failed live observations remain unchanged;
offline CLI replay validates the host contract, not model compliance or gains.
