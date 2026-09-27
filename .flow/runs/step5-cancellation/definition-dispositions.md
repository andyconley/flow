# Definition Dispositions: step5-cancellation

Sources:
- `adversarial-review.md`: architect findings F1–F21, with expertise lookup `no_match` (request `9b4ac899-…`).
- `adversarial-product.md`: product-manager findings P1–P6.

Engineer decisions on the findings (2026-09-27): **1b** (one slice, redesign live cancel inside it), **2a** (this slice before `v8-live-validation-3`), **3y** (runtime-cap interruption is an explicit case), **4y** (add a `flow run stuck` scan).

| Finding | Disposition | Where |
|---|---|---|
| F1 | Requirement changed. The handler uses a flag and raises once, only at interruptible waits, and the seal happens after the stack unwinds. The earlier "handler interrupts waits" assumption is rejected. | R2 |
| F2 | Requirement changed. Cancel takes no lock, its generation check is advisory, and the authoritative check happens at seal time. | R2, R3, AC1 |
| F3 | Requirement changed. The cancelled seal uses the abandon fences instead of the authority guard. | R2, AC1 |
| F4 | Requirement changed. A cancel request file is required, and a bare SIGTERM is treated as an interruption. | R2, R3, AC2b |
| F5 | Requirement changed. Owner generation versus lead generation is stated explicitly. | Generations section |
| F6 | Requirement changed. The receipt is built from the ledger with an `evidence_damage` list, and abandon runs no test. | R5, AC3(e) |
| F7 | Requirement changed. The seal releases grants, closes expansions and bumps the generation. | R5, AC1, AC3 |
| F8 | Requirement changed. The exclusion is exactly `{cancelled, abandoned}`, and a v7 `unknown` attempt still blocks. | R6, AC8 |
| F9 | Assumption confirmed. No late-evidence route is recorded as a consequence in the ADR. | R10 |
| F10 | Requirement changed. The start time is read independently of timezone, a machine id is recorded, and identity is re-checked before signalling. The macOS source is an open question for planning. | R1, R3, AC2 |
| F11 | Requirement changed. Groups whose leader has exited are reaped, and the supervisor uses `killpg`. A planning spike is needed. | R1, R4, AC4 |
| F12 | Requirement changed. The test runs in its own recorded group, the success criterion is limited to recorded groups, and Ollama server-side generation is a non-goal. | R1, success criteria, non-goals |
| F13 | Requirement changed. Recovery runs are covered, there is one control record per generation, and `recovery_in_progress` is a refusal. | R1, R4, AC3(c), AC4 |
| F14 | Requirement changed. Raising is disarmed after the outcome is recorded, the install and close order is specified, and `attempt_finished` is reported. | R2, R3, AC2c |
| F15 | **Rejected by the engineer (1b)**: kept as one slice. | — |
| F16 | Acceptance criteria changed: an expansion-paused abandon case, and abandon during a decision. | AC3(d), AC4 |
| F17 | Acceptance criteria changed. The ledger comparison is in the seal, not the validator, and lineage follows the existing convention. | R5, AC5 |
| F18 | Acceptance criteria changed. The mutation list was corrected, with mutations added for the cancel request and for disarm. | AC12 |
| F19 | Acceptance criteria changed: a registrar seam, a harness subprocess, FIFO synchronization, and a fake `claude` test. | R1, constraints, AC1c |
| F20 | Requirement changed: a reason-code table, and attempt status kept separate from expansion status. | Reason codes, R9 |
| F21 | Non-goal: SIGINT is unchanged, and `cancel_unsupported` covers a handler that couldn't be installed. | R2, non-goals, AC2 |
| P1 | **Rejected by the engineer (2a).** Abandon makes `v8-live-validation-3` recoverable, so this slice goes first. | — |
| P2 | **Rejected by the engineer (1b).** | — |
| P3 | Success criterion changed to "no surviving process from recorded groups". | Success criteria |
| P4 | Accepted (3y): the runtime-cap interruption is an explicit abandon case. | R4, AC3(b), AC7 |
| P5 | Accepted (4y): `flow run stuck`. | R9, AC10 |
| P6 | Accepted: the ADR notes that cancel and abandon are destructive where an approval is not. | R10 |
