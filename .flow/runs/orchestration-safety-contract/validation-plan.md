# Validation Plan: Orchestration Safety Contract

## Validation principles

- Prove both acceptance and refusal paths.
- For every failed lifecycle gate, compare `run.json` and `events.jsonl` before and after the attempt.
- Keep revision-1, revision-2, and `legacy/inferred` fixtures distinct.
- Validate the released artifact separately from the development checkout.
- Record whether mutation checks ran and what remains unverified when they do not.

## Unit validation

### Manifest and schema

- Valid minimal standard-risk manifest
- Valid delegated manifest
- Invalid JSON and wrong top-level types
- Missing required fields
- Unknown controlled-vocabulary values
- Unknown additive fields accepted
- Work-id mismatch
- Unsafe absolute or parent-traversal paths
- Missing referenced briefs or evidence

### Capability and assignment rules

- Every required capability confirmed
- Required capability missing
- Required capability unknown
- Read-only assignment with no write scope
- Output inside declared write scope
- Output outside declared write scope
- Duplicate assignment ids
- Missing success criteria or claim expectations

### Risk calculation

- One test for each hard trigger
- No hard trigger and zero aggravating factors
- No hard trigger and one aggravating factor
- No hard trigger and exactly two aggravating factors
- More than two aggravating factors
- Stored classification conflicts with calculated result

### Scope and concurrency

- Disjoint repository paths accepted
- Equal path overlap rejected
- Parent/child path overlap rejected
- Explicit serialized overlap accepted
- Same-target structural and additive concurrency rejected
- Same-target structural mutations serialized
- Distinct external targets accepted
- External region limitations reported accurately

### Claim and reconciliation rules

- All four claim classes accepted
- Unknown claim class rejected
- Observed claim has evidence reference
- Inferred claim links observations
- Recommended claim records decision ownership
- Unverified material claim cannot be promoted to accepted fact
- Every material conflict receives accepted, rejected, or deferred disposition
- Unresolved conflict blocks handback or acceptance

### Verification independence

- Standard risk records identities without requiring distinct verifier
- High-risk verifier differs from producer and evidence collector
- High-risk producer/verifier conflict rejected
- High-risk missing verification artifact rejected
- Human, agent, and external provider identities use the same structural contract

## CLI validation

- Text output for success and multiple failures
- JSON output has stable `ok`, `stage`, `manifest`, and `findings` fields
- Exit status is zero only on success
- Diagnostics name field, subject, rule, and corrective action
- Diagnostics do not include referenced artifact contents
- Missing run and missing manifest are distinguished

## Lifecycle integration

- New runs receive protocol revision 2
- Existing no-revision runs behave as revision 1
- `legacy/inferred` remains read-only and verifies successfully
- Revision-2 definition, solution, and plan approvals require and dispatch-validate the manifest
- Revision-2 handback runs handback validation
- Revision-2 review acceptance runs acceptance validation
- Optional scout manifest is validated when delegation or external mutation is declared
- Every refused transition leaves lifecycle projection and history unchanged
- Complete standard-risk revision-2 lifecycle reaches archive
- Complete high-risk shared-external-mutation lifecycle reaches archive only after independent acceptance

## Shared/external mutation simulation

Use a temporary local artifact as the stand-in external target while preserving the external protocol:

1. Capture target identity, version/hash, and baseline.
2. Declare a structural mutation and serialized owner.
3. Record recovery posture and exercise restoration in the fixture.
4. Apply the expected mutation.
5. Re-read and compare the target.
6. Inject an unexpected delta and prove handback refuses it until dispositioned.
7. Restore the expected state and record the result.
8. Have a distinct review fixture accept the evidence.

The test proves Flow's record and gates, not that arbitrary external APIs are transactional.

## Repository validation

Run at minimum:

```bash
/opt/homebrew/bin/python3.12 -m unittest discover -s tests
/opt/homebrew/bin/python3.12 scripts/regenerate-flow-help.py --check
flow sync claude --user --check
flow sync codex --user --check
flow doctor
flow runtime smoke --target all
git diff --check
```

Also exercise release staging so `cli/orchestration.py`, standards, templates, ADR, and documentation are included where the installer expects them.

## Generated-surface validation

- Regenerate both runtime targets from canonical sources.
- Compare command guidance and routing tables for semantic equivalence.
- Confirm managed manifests own the expected generated files.
- Use the manual runtime smoke guidance to verify command discovery, role invocation, and intended model/effort routing.

## Mutation testing

Run targeted manual mutations against:

- risk threshold (`>= 2` changed to `> 2`)
- required capability acceptance (`confirmed` weakened to `unknown`)
- overlap detection (parent/child case disabled)
- independent verifier identity comparison
- lifecycle refusal before write

For each, name the existing test that fails. Restore the implementation after each mutation. If any mutation is not run, record the exposed behavior explicitly.

## Review gates

- Lead-developer self-review against the plan
- Test-engineer review of proof and fault-detection coverage
- Architect review of lifecycle/artifact separation and compatibility
- Security-reviewer review of paths, sensitive evidence, external mutation, and destructive safeguards
- Quality-reviewer acceptance against the original requirements and acceptance criteria
- Independent provider review of the high-risk external-mutation fixture

## Release validation

Before push:

- Fetch `origin` and confirm the branch integrates without force.
- Inspect `git remote -v`.
- Inspect staged paths and final diff.
- Confirm canonical-checkout `docs/backlog.md` changes are absent.
- Confirm all required checks and review dispositions are recorded.

After push:

- Wait for semantic-release to complete.
- Verify the expected minor tag and GitHub release exist.
- Verify `CHANGELOG.md` contains the release section.
- Verify rendered release notes contain at least one entry.
- Verify the release commit is on `origin/main`.

Released-artifact proof:

- Install or update the tagged release in an isolated temporary home.
- Run setup and both runtime syncs.
- Run doctor and runtime smoke.
- Exercise `flow run validate-orchestration` from the released installation.
- Record the tag, commit, commands, outcomes, and any manual-runtime limitations.
