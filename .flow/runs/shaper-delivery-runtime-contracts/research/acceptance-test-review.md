## Acceptance Test Review

**Verdict: READY TO ACCEPT / ARCHIVE**

The approved Chunk 1 boundary is proved: Flow seals reviewed intent and a
charter, Magentic selects an eligible producer with a comparative rationale,
Flow grants and observes one scoped Claude edit and its targeted test, a
distinct Ollama verifier receives the observed evidence, and the receipt links
the authority chain. The deterministic suite also proves the relevant refusal
paths rather than relying on the live run alone. The latest authority fixes
have focused evidence, and the final required full-suite rerun has passed.

### Evidence reviewed

- Approved requirements, acceptance criteria, plan, and validation plan.
- Contract/control/projection/legacy/gateway/recovery/Magentic tests. I reran
  the seven focused modules after the new authority fixes: **82 tests passed**.
- Final post-fix full implementation suite: **1,321 passed, 1 skipped**, in
  138.060 seconds.
- Mutation evidence: reversing the approved-intent digest comparison made the
  lifecycle authority test fail, then restoring the source returned it to
  passing.
- Live v7 receipt `6ba14eb0b8dd4002a0392cb8f8ffc2c8`, its repair diff, and
  the isolated live worktree.

### Acceptance mapping

| Approved observable | Evidence | Result |
| --- | --- | --- |
| Clean, pinned worktree | Receipt baseline names `aecabc44a724b48924bd8fbce9c4f4eeae370b80` and records the approved file baseline. | Pass |
| One approved producer and comparative choice | Magentic chose `claude-producer` from the sealed Claude/Codex candidates, supplied a reason and a non-selection reason for Codex. The later two Codex proposals were denied as `producer_already_completed`. | Pass |
| Flow-controlled scoped edit and test | Receipt records exactly `docs/maf-adoption-design.md`, a bounded repair diff, and a Flow-run `test_documentation_contracts.py` result of `passed`. Direct inspection of the isolated worktree confirms the one-file, one-paragraph diff. | Pass |
| Distinct verifier | `ollama-verifier` is a separate, read-only assignment and made three physical calls only after the Flow-observed edit and test. | Pass for route/functionality |
| Complete authority-linked receipt | Completed receipt links Shaper Contract, Delivery Charter, handoff, and Delivery Lead generation 1. It has no pending approval or unknown action. | Pass |
| Fail-closed negative controls | Focused tests cover changed approved intent, stale generation, invalid/expanded roster, provider substitution, duplicate grants, verifier-before-observed-evidence, failed tests, transport loss, head drift, malformed/digest-mismatched v6, and recovery fences. | Pass |

### Newly reviewed authority fixes

- `test_changed_definition_source_before_start_plan_is_refused` mutates each
  approved requirements, acceptance-criteria, solution, and orchestration
  artifact separately. Each mutation refuses `start-plan`, creates no delivery
  authority, and leaves both `run.json` and `events.jsonl` byte-for-byte
  unchanged. This proves the authority check now covers all sealed input, not
  just Shaper intent.
- `test_unsupported_specialist_capability_is_refused` rejects vocabulary with
  no approved runtime projection. `test_delivery_charter_preserves_approved_capabilities_and_limits`
  proves the accepted capability mapping, prohibited capabilities, maximum
  instances, and numeric limits are retained in the charter.
- `test_read_only_approved_role_cannot_be_projected_as_editor` proves a role
  sealed as read-only cannot acquire edit capability through the runtime
  roster.
- `test_runtime_limits_are_projected_from_the_sealed_charter` proves the
  Delivery Lead envelope receives the exact smaller approved delegation,
  concurrency, replan, manager, and paid-worker limits rather than prior
  hard-coded defaults.

These behavior-level tests close the reported authority gaps without changing
the live proof's scope.

### Important limitation, accurately bounded

The live Ollama responses were repetitive and included invented inspection
claims. They establish a successful bounded provider route and evidence
handoff, not reliable independent semantic judgment. The existing
`validation-results.md` and `HANDOFF.md` state that limitation honestly.
Archive should preserve that wording; it must not say that Ollama independently
validated the documentation change's correctness.

The current contract requires a distinct verifier to review the Flow-observed
evidence, which the run did. It does not define a machine-checkable verifier
verdict schema or make semantic verifier quality an acceptance gate. A test
that rejects a malformed, incomplete, or failed verifier verdict is therefore
missing only for the next verifier-quality slice, not for this already-approved
runtime-route boundary.

### Conclusion

The post-fix full-suite gate passed. The receipt and deterministic proofs
support acceptance and archive. Carry forward structured verifier output, a
verifier-specific call cap, and fail-closed treatment of unusable verifier
verdicts as the next functional improvement.
