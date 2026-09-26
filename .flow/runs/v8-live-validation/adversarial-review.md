# Adversarial Review: v8-live-validation (definition)

- **Reviewers:** product-manager, business-analyst (expertise lookup: `no_match`) and solution-architect. All three ran read-only and in parallel from `briefs/adversarial-review.md` on 2026-09-26.
- **Orchestrator checks:**
  - `ollama list` shows `gemma4:26b`;
  - the Claude CLI is version 2.1.283;
  - the installed `flow` was updated from 0.35.x to v0.36.0;
  - the specialist digests recomputed from the installed release equal the sealed ones;
  - the envelope caps runtime at 600 seconds (`cli/execution_contracts.py:249`, `:257`).

## Findings and dispositions

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| A1 | blocking | A 5-call manager path (edit, then satisfied, with no review) gives no escalation, and nothing tells the manager that a review is needed. | **Requirement changed.** The job task now requires an independent read-only review by `local-verifier`, as a real job requirement, not staging. R4 and A3 now say the events are expected when the manager follows the task, and R6 covers the shorter path. |
| A2 | major | The ledger arithmetic for the 6-call path is correct (automatic grant at call 5, pending at call 6, answer-mode resume). | **Assumption confirmed.** |
| A3 | major | A failed review can't be repaired, because a second producer call is a hard denial. | **Requirement clarified** in R4. |
| A4 | major | Runtime is tight, the Ollama call is capped at 60 seconds, and runtime can't be expanded. | **Changed in part.** The recommended 900 seconds is invalid, because the envelope maximum is 600. Runtime stays at 600, noting that each launch gets its own deadline. An Ollama warm-up preflight is added, and timeouts are an environmental outcome in AC8. |
| A5 | major | The specialist digests could mismatch at prepare, after sealing. | **Verified and constrained.** The digests match installed v0.36.0. A preflight check is added, and R6 notes that a reinstall can invalidate a second attempt. |
| A6 | confirmed | Prepare accepts the manifest, roster and charter as drafted. | **Assumption confirmed.** |
| A7 | minor | The job charter isn't sealed or digested. | **Acceptance criterion changed:** the charter's sha256 is recorded at `approve-plan` and in the evidence. The sealing gap is a follow-up. |
| A8 | minor | Prepare doesn't prove the test fails at baseline. | **Acceptance criterion changed:** the baseline failure is recorded as evidence (AC9). |
| A9 | minor | `approve-definition` needs the four artifacts passed explicitly. | **Recorded** for the transition command. |
| A10 | minor | The CLI flags match; the installed version wasn't checked. | **Confirmed:** v0.36.0 installed. |
| P1 | major | The verifier model tag wasn't verified. | **Confirmed** present, and added to the preflight. |
| P2 | major | The outcome framing blurs validating the chain with delivering the documentation. | **Requirement changed:** validating the chain is the primary outcome, and the documentation is secondary and best effort. |
| P3 | minor | The wall-time target undercounts the worst case. | **Requirement changed:** about 30 minutes per attempt, with a two-attempt worst case of about 60 minutes. |
| B1, B3 | major | Environmental failures (Ollama down, auth expiry) aren't covered. | **Acceptance criterion changed:** AC8 adds an environmental outcome. A resume on the same attempt doesn't use up an attempt. |
| B2 | major | No outcome for an attempt that ends without a receipt. | **Acceptance criterion changed:** AC8 adds a no-receipt outcome. |
| B4 | minor | The verifier-retry evidence isn't named. | **Acceptance criterion changed** (AC9). |
| B5 | minor | Unclear whether the ACs apply per attempt. | **Changed:** AC1–AC9 apply to each attempt (R6, AC10). |
| B6 | minor | The stale-generation operator path isn't covered. | **Out of scope:** hermetic tests cover it (`test_expansion_decide`). If it happens live, it is a harmless refusal and is recorded if seen. |

## Framework follow-ups (for archive)
- The job charter isn't covered by sealed authority digests.
- Manifest `timeout_seconds` values are ignored for the Ollama verifier, which is hard-capped at 60 seconds.
