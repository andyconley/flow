# Reconciliation and review disposition

Date: 2026-09-19. Independent review: [review.md](review.md). Verdict: **request changes before adoption or acceptance**. All material claims below have an explicit disposition; deferred claims remain open work.

| Claim or finding | Disposition | Evidence and action |
| --- | --- | --- |
| MAF ran Codex, Claude, and Ollama in one concurrent workflow | Accepted as observed for read-only invocation | `research/mixed-provider-result.json`; three roles and provider/session metadata. Codex answer adherence remains unverified. |
| Flow pre-dispatch denials and Magentic plan-review request work | Accepted as isolated observations | `research/maf-delivery-result.json`, local `magentic_plan_probe.py` output. The integrated runtime delegation gate is **deferred**. |
| Separate-process checkpoint resume works for a stub request | Accepted as observed only for the stub | `research/restart_probe.py`; live worker recovery and Flow/MAF reconciliation are **deferred**. |
| Approved $10 paid spend boundary was respected | Rejected | Claude's measured cost was $3.264784, but Codex lacked an enforceable dollar cap or reliable run cost. Dispatch violated the stop rule. Further provider calls stopped and the historical script entry point was disabled. |
| One-task-per-provider plan bound | Rejected as followed | Two Codex and two Claude turns occurred due to preflight plus integrated proof; the first Codex result serializer failed. The deviation was recorded in `plan.md`. No further paid calls will be made in this run. |
| Receipt proves provider actions and commit | Deferred | `research/receipt.json` independently checks definition digests and clean Git baseline but imports provider metadata and has no worker commit or action attestation. |
| MAF eliminates roughly 70% of Delivery Lead machinery | Deferred | `validation-results.md` lists covered functions and remaining Flow-owned work; no weighted denominator exists. |
| MAF earns the runtime layer now | Rejected | The hard cost and dynamic delegation boundaries failed or remain untested. Keep MAF as preferred candidate; preserve freeze on Flow-native engine work while a corrected bounded test is designed. |

Review suggestions accepted: the first-pass decision is now labeled historical; the integrated script is disabled pending a Codex cost guard. Provider-level timeout/cancellation and charter-digest recomputation remain next-slice requirements.
