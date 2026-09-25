# Handoff: shaper-expansion-approval (MAF adoption step 5, slice 1)

- **Status:** implementation complete and ready for `flow-review`.
- **Branch:** `codex/step5-shaper-approval-design`, not pushed. It will become one PR.

## What shipped

Delegated expansion for chartered protocol v8 (ADR 0017):

- **Sealed headroom.**
  - Shaper intent may carry `expansion_headroom` for delegations, paid worker calls, verifier calls, manager calls and manager rounds.
  - The v3 Shaper Contract and Delivery Charter seal it, and `delegated_expansion` is derived from it.
  - The runner ceilings live in `runtime/maf_runner/limits.py`. The runner, the v8 supervisor guards, envelope validation and contract validation all read them from there.
- **Requests and automatic grants.** A v8 denial that fails only expandable limits records a Flow-computed request: one unit per limit, keyed on the denied row. Within the lineage's remaining headroom it is granted in the same transaction and the run continues. Hard denials, and units past a ceiling, never create requests.
- **Pause.** An escalated request stops the run as `expansion_paused`:
  - nothing is sent, the attempt stays started, and the claim keeps its generation;
  - `flow run status` and `list` show `decide expansion <request>`;
  - `inspect-delivery` shows the requests, grants, remaining headroom and the escaped rationale.
- **Decide.** `flow run decide-expansion <work> <attempt> <request> --approve|--deny --expected-generation N --actor A --explanation E`:
  - it is fenced and generation-checked, and follows the ADR 0016 lock order;
  - it refuses, changing nothing, on a stale generation, an unknown or already-decided request, an attempt that is not truly paused, an inactive lead, or a grant past a ceiling.
- **Resume.** `recover-delivery-lead` replays the paused proposal under the decision:
  - **Worker:** `pending` mode. The same action id runs once under the grant, or the denial is reported to the manager.
  - **Manager, approved:** `answer` mode from the latest worker checkpoint, or `restart` when there are no actions.
  - **Manager, denied:** the attempt is sealed `failed` with the limit as the reason.
- **Lifecycle.** Supersede or resume cancels pending requests and lapses unused grants, a release closes them, and so does sealing.
- **Receipts.** An `expansion` block is added, validated by recomputing headroom and effective limits in order, and compared with the ledger at seal time.

## Proof

- **Suite:** 1537 tests, OK, 0 skipped, with `FLOW_MAF_PYTHON`.
- **End to end:** 5 cases against the real pinned Magentic runner.
- **Mutations:** M1–M10 each caught.
- **Details:** `validation-results.md` has the acceptance-criteria-to-test mapping; `implementation-review.md` has the quality and security findings, all dispositioned.

## Approved amendments to the acceptance criteria

These are in `plan.md`, "Amendments from plan review (binding)":

- **AC6:** the row goes `denied` → `allowed` (`expansion_granted`), and the denial is kept.
- **AC7 (E5a):** a manager deny seals the attempt failed.
- **AC8 (E6a):** a grant follows the scope of the counter it raises.

## Residual risks

- **Replay identity depends on the pinned MAF version.** `tests/test_maf_expansion.py` must pass on any pin change.
- **No live run yet.** Expansion is proven hermetically only. It still needs validating in real-world runs.
- **The `restart` mode is new.** It is allowed only with zero action rows and every earlier manager call completed.
- **A decide can queue up to 10 seconds** behind another decide.

## Follow-ups

- Real-world validation runs (the next sequencing step).
- The remaining step 5 pieces: cancellation, trace correlation, an MCP handback and a token cap. Replan expansion and the optional specialist pool (deferred under E1 and E2).
- **Capability gaps to record at archive:**
  - approved definition artifacts and the orchestration manifest can't be amended after sealing, so plan-lane amendments had to live in `plan.md`;
  - `project-test-command-declaration` recurred, because the fail-closed suite had to be hand-scripted.
