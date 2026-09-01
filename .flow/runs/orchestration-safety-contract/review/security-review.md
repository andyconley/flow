# Security Review: Orchestration Safety Contract

## Security Review Summary

### Summary

- Critical: 0
- High: 0
- Medium: 0
- Low: 0
- Verdict: pass; no open security finding blocks acceptance or release.

### Findings

No open findings remain in the reviewed change.

### Remediated During Review

#### [HIGH, remediated] Shared mutation could omit the high-risk trigger

- Location: `cli/orchestration.py`, dispatch risk validation and acceptance validation
- Description: The first reviewed revision calculated risk only from the trigger list supplied by the manifest. A non-read-only shared mutation could therefore remain standard-risk by omitting `production_or_shared_external_mutation`.
- Impact: A production or shared external mutation could reach acceptance without independent verification.
- Exploitation scenario: A producer declared `mode: shared-mutation` and a structural external target, omitted the hard trigger, and reused its own identity for producer, evidence collector, and verifier. The initial validator returned no acceptance findings.
- Recommendation: Derive a mandatory hard-trigger constraint from every non-read-only shared target and apply the calculated high classification. Implemented and covered by `test_shared_mutation_requires_calculated_hard_trigger`.
- Retest: The validator now refuses the omitted-trigger case and requires the high-risk acceptance controls.

#### [HIGH, remediated] Verification identities were not bound to assignment roles

- Location: `cli/orchestration.py`, `_validate_acceptance`
- Description: The first remediation checked that identities appeared somewhere in the assignment inventory, but it did not bind producer, evidence collector, and verifier roles to specific assignments. With two declared providers, their labels could be swapped so the actual producer appeared to be independent.
- Impact: A producer could certify its own high-risk work while the manifest claimed an independent verifier.
- Exploitation scenario: A writable assignment used `producer-agent`, a read-only assignment used `reviewer-agent`, and verification labeled the reviewer as producer and `producer-agent` as verifier. The intermediate validator returned no findings.
- Recommendation: Reference assignment ids for verification roles, derive identities from each assignment, require every writable and mutable-target owner assignment in `producer_assignments`, and require a distinct read-only verifier assignment for high-risk acceptance. Implemented and covered by `test_acceptance_cannot_swap_producer_and_verifier_role_labels` and the high-risk identity tests.
- Retest: The swapped-role probe now returns `writable-producer-binding`, `shared-mutation-producer-binding`, and `read-only-high-risk-verifier`. A correctly separated read-only verifier passes.

#### [MEDIUM, remediated] Run ids could escape the run directory

- Location: `cli/runstate.py`, run path construction; `cli/orchestration.py`, manifest path construction
- Description: `work_id` was used as a path component without validation.
- Impact: A crafted local CLI argument could create `run.json` and `events.jsonl` outside `.flow/runs` within the caller's writable filesystem.
- Recommendation: Restrict work ids to one safe path component before any read or write. Implemented with `valid_work_id` and covered by `test_work_id_traversal_is_refused_without_writing`.
- Retest: The controlled traversal fixture is refused without creating an outside file.

#### [MEDIUM, remediated] Directories satisfied evidence existence checks

- Location: `cli/orchestration.py`, `_path_exists`
- Description: An existing directory could be supplied where the contract required an artifact file.
- Impact: Baseline, readback, comparison, reconciliation, or verification evidence could be structurally satisfied without an evidence document.
- Recommendation: Require a regular file after repository containment and symlink resolution. Implemented and covered by `test_artifact_references_must_be_regular_files`.
- Retest: A run directory supplied as the verification artifact now returns `referenced-artifact-exists`.

#### [MEDIUM, remediated] Irreversible acknowledgment required no safeguards

- Location: `cli/orchestration.py`, shared-state handback validation
- Description: A destructive mutation using `irreversible_acknowledged` passed without the safeguards promised by the standard and template.
- Impact: Destructive work could pass handback with neither exercised recovery nor a recorded compensating control.
- Recommendation: Require non-empty `recovery_safeguards` when recovery is irreversibly acknowledged. Implemented and covered by the mutation recovery test.
- Retest: The destructive fixture without safeguards now returns `irreversible-safeguards`.

#### [LOW, remediated] Malformed nested reference ids raised exceptions

- Location: `cli/orchestration.py`, shared-state owner, claim-support, and verification-assignment lookups
- Description: After nested controlled enums were made type-safe, JSON objects supplied as `owner_assignment`, an inferred claim support id, or a producer-assignment id still reached set or dictionary lookups and raised `TypeError`.
- Impact: A malformed local manifest could stop validation with a traceback instead of returning controlled findings. The lifecycle gate failed closed, but diagnostic behavior was not robust at the untrusted JSON boundary.
- Recommendation: Validate every reference id as a non-empty string before membership or lookup and normalize invalid producer lists to an empty safe set. Implemented and covered by `test_malformed_nested_reference_ids_return_findings`.
- Retest: The three independent malformed shapes now return `known-assignment-owner`, `inference-support`, and producer-inventory/binding findings without an exception.

### Positive Observations

- Repository paths reject absolute paths, parent traversal, and symlink escapes after resolution. Output paths are checked against declared write scopes, and read-only reports are confined to the containing run.
- Structural and destructive operations on the same external target must share serialization even when their declared regions differ. Concurrent additive work is limited to declared different regions, with the declaration-level limitation surfaced in CLI output.
- High-risk verification now derives stable identities from explicit assignment ids. Every writable assignment and mutable shared-state owner is treated as a producer, while the verifier must be a distinct read-only assignment and provider.
- Destructive work requires exercised recovery or an irreversible acknowledgment with recorded safeguards. Handback also requires baseline, execution, readback, comparison, and unexpected-delta disposition artifacts.
- Invalid JSON diagnostics disclose line and column but not manifest contents. Findings use controlled messages and do not echo sensitive artifact contents.
- Lifecycle orchestration checks run before `_write_run` and `_append_event`. Refusal tests compare both files byte-for-byte and confirm that failed dispatch, handback, acceptance, and traversal checks leave lifecycle state unchanged.
- Revision-1 and `legacy/inferred` compatibility remains explicit; revision-2 gates fail closed on missing manifests and unsupported controlled values.

### Recommendations

- Treat the manifest as declaration-level safety evidence, not an authorization boundary. Runtime capability grants, identity ownership, external-region aliases, evidence truth, and baseline freshness remain human or adapter responsibilities as documented.
- Consider a future optional adapter check for RFC 3339 baseline timestamps, source versions or hashes, and maximum baseline age. This is hardening, not a blocker for the current structural validator.
- Consider emitting the manifest path relative to the repository in machine output when portability or log minimization matters. The current absolute path is low-risk for a local CLI and does not expose manifest content.

## Independent Verification Evidence

- Reviewed requirements and acceptance criteria in `.flow/runs/orchestration-safety-contract/` and the architecture/current-state research inventory under `research/`.
- Reviewed `cli/orchestration.py`, `cli/runstate.py`, `cli/flow.py`, the orchestration standard/templates, and the orchestration test classes in `tests/test_flow.py`.
- Ran `python3 -m unittest tests.test_flow.OrchestrationValidationTests tests.test_flow.OrchestrationCliTests -v`: 25 tests passed.
- Independently instantiated the synthetic high-risk external-mutation fixture represented by `OrchestrationValidationTests._add_shared_mutation`. With a distinct read-only reviewer assignment, acceptance returned no findings. Replacing that verifier with the producer returned `independent-high-risk-verifier` and `read-only-high-risk-verifier`.
- Independently probed omitted shared-risk classification, swapped producer/verifier roles, directory evidence, irreversible acknowledgment without safeguards, structural concurrency, repository traversal, malformed nested controlled values and reference ids, and lifecycle refusal atomicity. The remediated validator refused each unsafe form without an uncaught exception.
- Ran `git diff --check`: passed.

## Residual Risk

The remaining risk is the intended boundary of a structural local validator: declarations and regular-file existence can be checked, but the CLI cannot prove external identity ownership, semantic correctness, the truth of evidence contents, or actual runtime grants. The standard and JSON result limitations state that boundary, and high-risk acceptance adds a distinct verifier instead of claiming the CLI can establish those facts.
