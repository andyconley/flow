# Acceptance Criteria

Status: **approved by the engineer on 2026-09-23.**

Chunk 1 covers the evidence-free boundaries. Chunk 2 covers continuation after operator resolution.

1. **Scope refusals.** The explicit recovery command accepts a non-terminal v8 chartered attempt. It refuses each of the following with a stable reason:
   - a v6 attempt;
   - a v7 attempt;
   - a terminal attempt.

   A before-and-after ledger snapshot and receipt comparison proves that none of these refusals mutates anything. v5 resume and recover tests are unchanged and passing.
2. **Explicit, exclusive invocation.** No path resumes an attempt without the command: not elapsed time, grant expiry, or process exit. Two concurrent recovery commands on one attempt give exactly one recovery, and the other fails closed. Re-invoking after a completed recovery returns the current state with no further ledger mutation.
3. **Ledger first.** A checkpoint that holds a queued call produces no provider send without a Flow grant. The worker and manager adapter call counts stay at zero until the ledger authorizes a call.
4. **Kill-boundary matrix.** Each boundary below has a deterministic test that kills the attempt, then recovers it explicitly. Each test asserts the terminal state, the exact ordered list of provider sends, and the receipt.
   - Chunk 1:
     - (b) producer grant unconsumed;
     - (d) producer completed, verification incomplete;
     - (f) verifier completed, not evaluated;
     - (g) after a retry-eligible evaluation;
     - (h) after a terminal evaluation;
     - (i) interrupted receipt sealing, using a new pre-seal test seam;
     - a clean transport loss with no uncertain sends.
   - Chunk 2:
     - (a) manager call `started` or `unknown`;
     - (c) producer send claimed, no response;
     - (e) verifier send claimed, no response.
5. **Resolution binding (chunk 2).**
   - In boundaries (a), (c), and (e), the call stays `unknown` and recovery is refused until a resolution exists that is bound to that action id, attempt id, and generation. A resolution recorded against any other attempt or action does not unblock it.
   - After `resolved_completed`, recovery continues with zero resends. For a verifier, the recorded response is evaluated under the v8 contract.
   - After `resolved_not_dispatched`, the action may be re-granted.
6. **Test evidence reuse.** A v8 attempt is killed after its verifier returns `valid_pass`, with an injected test runner that returns a new digest on every call. On recovery it reaches `completed`, and that test runner is **never invoked**. The final evaluation is bound to the reused `verifier_inputs.test_digest`. At boundary (d), before any verifier input exists, the test runner is invoked exactly once.
7. **Worktree drift.** When the worktree no longer matches the recorded diff, recovery fails closed with a stated reason. It makes no provider send and marks nothing complete.
8. **Limits and allowance.** A proven-unsent action that is re-granted counts once against the chartered delegation, paid-call, and verifier limits. A recovered verifier retry is granted only when the latest evaluation is `valid_fail` or `unusable` and allowance remains. Otherwise it is denied before any adapter is called.
9. **Lead authority.**
   - Recovery is refused once the envelope's lead-claim generation is no longer active.
   - After an explicit lead resume or supersede, the old attempt has a terminal superseded record.
   - At the function seam, a lead resume or supersede is refused while any action of the run's active attempt is `unknown`.
   - Abandonment still succeeds while actions are `unknown`.
10. **Truthful receipt.** The recovered or linked receipt records the recovery, the owner generation, and the resolutions relied on. Receipt validation rejects each of these tampering cases in a separate subtest:
    - a changed generation;
    - a removed resolution;
    - an added resolution;
    - a removed recovery marker.

    A completed v7 receipt still validates unchanged.
11. **Inspection.** `flow run inspect-delivery` on a v8 attempt reports whether it can be recovered, lists each blocking action with its reason, and names the evidence each one needs.
12. **Suite and mutation checks.** The full repository suite passes, including the new focused recovery tests. Two named assertions must each fail when their guard is removed, and each is shown to do so by a mutation check:
    - worker adapter calls equal zero when boundaries (c) and (e) are recovered;
    - test runner calls equal zero for AC6.
