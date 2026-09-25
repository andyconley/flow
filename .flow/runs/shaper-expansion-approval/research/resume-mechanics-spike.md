# Spike: resume mechanics for an expansion pause

- **Question:** can a paused Delivery Lead attempt resume so the denied proposal comes back with the *same identity*, for both worker actions and manager calls, without Magentic proposing something new? This is assumption A4.
- **Method:** hermetic runs against the real MAF runner (`runtime.maf_runner.delivery_lead`, protocol v8), using the pinned interpreter `FLOW_MAF_PYTHON` (agent-framework-core 1.19.0, agent-framework-orchestrations 1.2.0) and stub responses. The scripts are `spike_expansion.py` and `spike_expansion2.py` in this folder.
- **Date:** 2026-09-25.

## Findings

| # | Scenario | Result | Evidence |
|---|---|---|---|
| S1 | A worker proposal Flow never answered, restored in `pending` mode from its checkpoint | Re-emitted with the same `action_id`, `checkpoint_id` and sequence | Existing test `tests/test_maf_delivery_lead.py::test_unanswered_action_restores_in_pending_mode_with_its_original_identity`. A denied row differs only on the ledger side, not in MAF. |
| S2 | A manager call after action 1, left unanswered as if denied; child killed; restored in `answer` mode from action 1's checkpoint | Re-issued with an identical sequence, phase, round, prompt digest and `call_id` | Spike S2 |
| S2b | The same, for the call after action 2, restored from action 2's checkpoint | Identical `call_id` | Spike S2b |
| S3 | Fresh restart with the same envelope, including `checkpoint_dir` | The planning calls (facts, plan, first progress) have identical prompts and `call_id`s | Spike S3. The first attempt used different checkpoint directories, which changes the envelope digest and so every `call_id`. |

## Implications

- **A4 is confirmed** for both kinds of proposal.
  - **Worker denial:** restore in `pending` mode from the denied proposal's checkpoint. This requires binding that checkpoint at denial; today it is bound only when the proposal is allowed.
  - **Manager denial:** restore from the latest bound worker checkpoint, in `answer` mode. Completed manager calls after that checkpoint replay under the same `call_id`, so the gateway answers them from the ledger (the existing `duplicate_manager_request` path) and the denied call arrives again under its own ID.
  - **Manager denial before any worker checkpoint:** a fresh restart replays deterministically. This needs a new "restart" resume mode.
- **The envelope must stay byte-identical across a pause,** including `checkpoint_dir`. A grant must not alter the envelope. Grants live in the ledger, which is consistent with the no-re-seal non-goal.
- **Prompt determinism depends on the pinned MAF version.** A MAF upgrade could break replay identity. A MAF-gated regression test is needed (recorded as a risk).
