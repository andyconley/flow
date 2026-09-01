# Support Caveats: Orchestration Safety Release

## Support Readiness Summary

### Symptom

- `flow run validate-orchestration` can fail at `dispatch`, `handback`, or
  `acceptance` with a structured finding. The finding identifies the field,
  subject, rule, and corrective action; it does not print referenced evidence.
- A passing validator means the declared contract and local file references
  are structurally acceptable. It does not mean a runtime granted a declared
  capability, that an identity owns the work, that evidence is semantically
  true, or that an external API behaved transactionally.
- Runtime smoke includes four manual Claude/Codex discovery and model-routing
  checks. They confirm that the client can discover the generated surface and
  that routing evidence can be inspected; they do not prove that the client
  honored the configured model/effort, granted a capability, or honored an
  external-provider identity.
- New runs use protocol revision 2 while keeping `run.json` schema 1. Runs
  without `protocol_revision` are revision 1 and retain prior behavior;
  `legacy/inferred` folders remain readable and do not acquire lifecycle state.

### Diagnosis

1. Capture the work ID, stage, command, exit code, and complete structured
   finding (`--json` is preferred). Do not paste sensitive evidence contents.
2. Confirm the referenced path is inside the run and is a regular file, then
   inspect the named manifest field and its assignment/output ownership. For a
   later-stage failure, check the required reconciliation, fresh baseline,
   readback/comparison, recovery, and unexpected-delta records.
3. If the finding concerns capabilities, identity, semantic evidence, or an
   external mutation, collect the runtime/provider log and human confirmation;
   do not treat a green local validator as proof. For high-risk work, confirm
   the verifier is a distinct read-only assignment from the producer.
4. For a suspected lifecycle refusal, compare `run.json` and `events.jsonl`
   before and after. A correct refusal leaves both byte-for-byte unchanged.

### Resolution

- Workaround: correct the manifest or add the missing run artifact named by
  `next_action`, then rerun the same cumulative stage. Use the prior revision-1
  path only for an existing revision-1/legacy run; do not retrofit a manifest
  merely to bypass a refusal.
- Permanent fix path: update the assignment/evidence contract and tests, record
  the disposition in the run, and have an independent read-only verifier
  re-check high-risk acceptance. External recovery or provider behavior must be
  demonstrated by the adapter/operator, not inferred from this CLI.

### Escalation

- Escalate when: a published install cannot import the orchestration command;
  an update leaves an incomplete install; a refusal changes lifecycle files;
  semantic-release publishes the wrong tag/notes; or external state differs
  from the recorded baseline/readback.
- Include: exact source SHA, release tag and commit, work ID, stage, JSON
  finding, command/exit code, hashes before and after any refusal, install mode
  and isolated-home path, runtime/client used, and the relevant evidence paths.
  Redact credentials, secrets, and raw external exports.
- Route to: support for declaration/path corrections; engineering for validator
  or lifecycle behavior; release owner for semantic-release/tag/changelog or
  install/update failures; security/SRE for identity, unauthorized mutation,
  recovery, or unexpected external deltas.

### Follow-ups

- FAQ / macro updates: add “passing validation is not authorization,” revision-1
  compatibility, the four manual runtime checks, and the required diagnostic
  bundle to the release/runbook support macro.
- Product or engineering feedback: automate the currently manual pre-push and
  released-install gates in CI. If semantic-release or external-mutation proof
  fails after publication, repair forward: preserve the published artifact,
  record the failure and affected SHA/tag, publish a corrective conventional
  commit/release, and rerun fresh tagged install/update and runtime checks.
  Never rewrite history or claim pending tag, GitHub release, changelog, or
  released-install evidence from candidate-tree results.
