# Provider Selection Runbook

- Subject: Protocol v9 provider selection, dispatch, recovery, and rollback
- Scope (versions, environments): Protocol v9 chartered delivery on local Flow hosts
- Owner role: Flow operator
- Reviewed: 2026-10-02

Use the exact work and attempt identifiers from the failed command. Preserve
the ledger, receipt, trace, and selection evidence. Never edit those artifacts,
retry a claimed send, bypass confinement, or infer that a missing response means
the provider did not receive the request.

## Every candidate is stale or unavailable

- Normal case: The readiness snapshot expired, the required Ollama model is not
  installed, a hosted CLI is logged out, or its credential artifact cannot be
  projected into an isolated worker home.
- Confirm it's a fault: Run
  `flow run provider-selection-probe WORK_ID --json` and inspect each candidate's
  readiness state and controlled `evidence_code`.
- Diagnosis steps (if fault):
  - For Ollama, confirm the configured model is present and the local service is reachable.
  - For a hosted candidate, confirm the CLI exists, its bounded authentication-status
    command succeeds, and its credential artifact is a regular non-symlink file.
- Remediation (if fault): Restore the local service or authenticated CLI session,
  or narrow/disable the unusable candidate in policy. Run the read-only probe again;
  do not hand-edit readiness evidence.
- Escalate to: Flow maintainer
- Escalate when: Readiness remains stale or unavailable after the local dependency
  is healthy, or the probe emits an undocumented evidence code.

## Flow falls back before sending

- Normal case: A candidate positively refuses readiness before its durable send
  claim, so Flow selects the next eligible sealed candidate.
- Confirm it's a fault: Run `flow run trace WORK_ID --attempt ATTEMPT_ID --json`
  and confirm the predecessor action is `pre_send_refused`, not consumed or unknown.
- Diagnosis steps (if fault):
  - Compare the refusal evidence with the sealed catalog and effective policy.
  - Confirm the successor was selected from the existing sealed candidates and
    that no provider action was claimed for the refused candidate.
- Remediation (if fault): Repair the readiness dependency for future attempts or
  narrow policy. Do not replay or rewrite the current attempt's selection history.
- Escalate to: Flow maintainer
- Escalate when: Fallback follows a claimed send, selects outside the sealed
  candidate set, or cannot be explained by controlled refusal evidence.

## A provider send is claimed but its outcome is uncertain

- Normal case: A process, transport, or response failure after the durable send
  claim leaves the action unknown; automatic fallback is intentionally blocked.
- Confirm it's a fault: Run
  `flow run v9-recovery-status WORK_ID ATTEMPT_ID` and confirm reconciliation is required.
- Diagnosis steps (if fault):
  - Inspect `flow run inspect-delivery WORK_ID --attempt-id ATTEMPT_ID --json`.
  - Correlate the claimed action in `flow run trace WORK_ID --attempt ATTEMPT_ID --json`
    with provider-side evidence without sending the task again.
- Remediation (if fault): Reconcile the external outcome when evidence is conclusive.
  Otherwise terminate the attempt as cancelled or abandoned with an actor and
  explanation; never fall forward from an uncertain claimed send.
- Escalate to: Delivery lead
- Escalate when: Provider-side evidence conflicts with the ledger, reconciliation
  cannot establish an outcome, or duplicate execution is plausible.

## A selected model is at capacity

- Normal case: The hosted adapter records `model_capacity` with
  `observed_not_executed`, charges zero, excludes that candidate for the current
  logical assignment, and selects the next eligible sealed candidate.
- Confirm it's a fault: Inspect `flow run trace` and verify the action and
  selection both show `observed_not_executed`; the successor must name that
  selection as its predecessor.
- Diagnosis steps (if fault): Confirm the transcript contained no agent/tool
  execution event, the candidate was attempted only once, and the successor
  came from the sealed catalog and policy.
- Remediation (if fault): If all candidates are exhausted, restore capacity or
  change approved policy for a new attempt. Never relabel an unknown send as a
  capacity refusal or hand-edit its charge.
- Escalate to: Flow maintainer
- Escalate when: Capacity is charged as an unobserved send, fallback repeats a
  candidate, or any execution evidence coexists with `observed_not_executed`.

## A legacy manifest-linked charter cannot enter v9

- Normal case: Protocol v9 requires an approved `artifacts.job_charter` digest;
  legacy compatibility alone does not create that authority.
- Confirm it's a fault: Run the read-only provider-selection probe and preserve
  its absent-charter refusal.
- Remediation: Prepare a complete provider-neutral successor inside the same run,
  then run `flow run migrate-job-charter-v9 WORK_ID --replacement PATH --reason TEXT --approved-by-user`.
  Omit the replacement only if the canonical predecessor is already v9-complete.
  Re-run the probe after the migration succeeds.
- Escalate to: Delivery lead
- Escalate when: The command reports path, symlink, digest, active-attempt,
  schema, topology, or authority-expansion refusal. Do not bypass it by editing
  `run.json` or historical receipts.

## Cancellation or abandonment does not seal the attempt

- Normal case: Termination may wait while a live owner performs its fenced shutdown;
  the attempt remains non-terminal until the receipt is sealed.
- Confirm it's a fault: Re-run `flow run v9-recovery-status WORK_ID ATTEMPT_ID`
  and inspect the attempt state and active owner generation.
- Diagnosis steps (if fault):
  - Confirm the requested actor, explanation, status, and owner generation are current.
  - Inspect the trace for a live send, competing recovery, or already-terminal attempt.
- Remediation (if fault): Use
  `flow run terminate-v9-delivery WORK_ID ATTEMPT_ID --status cancelled|abandoned --actor ACTOR --explanation TEXT`
  with the intended terminal status. Do not kill processes or edit the ledger by hand.
- Escalate to: Delivery lead
- Escalate when: A live process cannot be fenced, ownership is inconsistent, or
  termination reports success without a sealed terminal receipt.

## A hosted worker reports sandbox launch failure

- Normal case: Never; Flow must refuse the hosted send when macOS confinement
  cannot be established.
- Confirm it's a fault: Inspect the attempt trace and receipt for the sandbox
  application failure and confirm the adapter did not complete normally.
- Diagnosis steps (if fault):
  - Confirm the host supports the required sandbox launcher and the provider
    executable resolves to the expected regular file.
  - Check staged read/write scopes and the isolated credential home without
    broadening them or exposing credential contents.
- Remediation (if fault): Repair the host launch environment or disable the hosted
  candidate for new attempts. Do not bypass or weaken confinement.
- Escalate to: Security maintainer
- Escalate when: Confinement cannot be restored, protected-path access may have
  occurred, or a code change to the sandbox profile is required.

## Receipt verification fails

- Normal case: Never for an intact sealed receipt and ledger; `not_applicable` and
  documented `unverifiable_offline` checks are not failures.
- Confirm it's a fault: Run
  `flow run verify-receipt WORK_ID --attempt ATTEMPT_ID --json` and identify the
  first check whose verdict is `fail` or whose receipt cannot be read.
- Diagnosis steps (if fault):
  - Compare the reported row, key path, expected value, and observed value.
  - Preserve the receipt, ledger, sealed authority, and command output before
    investigating storage damage or a verifier defect.
- Remediation (if fault): Do not edit or regenerate the receipt. Quarantine it from
  acceptance and correct the producing code in a new attempt when appropriate.
- Escalate to: Flow maintainer
- Escalate when: Tampering or data loss is plausible, multiple checks fail, or the
  verifier disagrees with intact ledger facts.

## New starts must stop using a candidate or protocol v9

- Normal case: Policy rollback affects only new starts; existing attempts and
  receipts retain their sealed selection and recovery semantics.
- Confirm it's a fault: Run `flow run provider-selection-probe WORK_ID --json`
  for a not-yet-started job and confirm the unwanted candidate still survives policy.
- Diagnosis steps (if fault):
  - Identify the administrator or project policy layer that authorizes the candidate.
  - Confirm whether the rollback targets one candidate, a provider family, or all
    new protocol v9 execution.
- Remediation (if fault): Disable or narrow candidates in Flow policy for new starts.
  Preserve existing attempts; use `--legacy-v8` only for an already approved
  historical v8 contract, never to bypass a v9 denial.
- Escalate to: Flow administrator
- Escalate when: Policy cannot exclude the candidate deterministically, an active
  attempt would need rewriting, or stopping all new v9 starts requires a release change.

## Post-incident follow-up

- Record the work ID, attempt ID, exact source SHA, controlled evidence codes,
  receipt-verification result, operator action, and any policy change. Never attach
  secrets or raw authentication-status output.
