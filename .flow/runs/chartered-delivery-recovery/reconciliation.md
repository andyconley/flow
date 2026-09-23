# Discovery Reconciliation

This file records the conflicts between the discovery role notes, and how each was resolved.

1. **Test re-verification on resume**
   - `failure-scenarios.md`, boundary 4, says re-running the edit and test checks on resume is idempotent and safe.
   - `recovery-boundary.md` (the evidence-reuse and stale-evidence rows) shows otherwise. The targeted test's output digest changes on every run, so the stale-evidence gate rejects every resumed v8 pass.
   - **Resolution:** the architecture evidence stands, and the coordinator confirmed it in the v8 branch (`delivery_gateway.py:552-564` and `:999-1004`). The diff re-check stays, because it is deterministic. Test evidence is reused (Req 6).
2. **Unknown blocking a lead change**
   - `failure-scenarios.md`, boundary 9, says lead-claim change already refuses while an action is `unknown`.
   - `recovery-boundary.md` says the checked field, `pending_unknown_actions`, is never written.
   - **Resolution:** the coordinator's grep confirms the field is read only at `delivery_control.py:239`. It becomes a requirement (Req 10).
3. **Lost-response scope**
   - `increment-scope.md` defers lost-response `unknown` handling.
   - `failure-scenarios.md` wants a reconcile-then-resume path.
   - **Resolution:** automatic provider-evidence discovery is deferred. Continuing after an operator resolution recorded through the existing `resolve_unknown` is in scope (Req 4, AC5). The engineer must confirm this at approval.
4. **CLI for lead resume and supersede**
   - `failure-scenarios.md` could not find an operator command for it.
   - **Resolution:** the coordinator confirmed that `change_lead_claim` has no caller in `cli/`. It is recorded as an open question for the engineer.
