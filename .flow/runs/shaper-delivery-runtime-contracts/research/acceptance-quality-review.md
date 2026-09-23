## Review Summary

### Verdict

- **Ready to accept/archive**

The three authority-boundary defects found during acceptance review are resolved. Flow now binds every approved source before transition, preserves and enforces approved specialist capabilities and policy limits, and carries the sealed runtime limit through the v7 envelope into Magentic plus every configured provider route.

### Findings

#### Critical

- None.

#### Important

- None.

#### Suggestions

- Add the data review's durable SQLite migration marker before v7 becomes a long-lived schema surface.
- Improve the Ollama verifier's structured evidence contract and introduce a verifier-specific call cap; the live route is functional, but three repetitive verifier calls supplied weak semantic evidence.
- Replace mtime-based default attempt selection and add explicit deletion evidence in later operability work.
- If a later policy needs one cumulative wall-clock budget across all sequential callbacks, define and enforce a remaining-time budget separately. This slice consistently applies `runtime_seconds` as the supervisor and per-call ceiling.

### Resolved Findings

1. **Approved-source mutation between approval and `start-plan`: resolved.**
   - `cli/runstate.py:476-493` records requirements, acceptance criteria, Shaper intent, and orchestration digests at Definition approval and the solution digest at Solution approval.
   - `cli/delivery_control.py:132-135` compares every selected source with its approved digest before staging authority.
   - The former reproduction now fails closed: changing requirements after approval makes `start-plan` return `False` with `approved requirements changed after approval`, and no Delivery authority is created.

2. **Specialist capabilities and numeric limits widened by hardcoded defaults: resolved.**
   - `cli/delivery_contracts.py:98-141` validates a closed capability vocabulary, maximum instances, delegation limits, and enforceable safety fields. Lines 180-202 preserve those values in the Charter, including prohibited capabilities.
   - `cli/delivery_gateway.py:315-326` requires runtime capabilities to be subsets of sealed role authority and enforces roster cardinality and delegation bounds.
   - The former narrowed-limit reproduction now preserves delegation `1`, concurrency `1`, replans `0`, and paid calls `1`. A reviewer role projects only `read`, and the read-only-as-editor test rejects expansion before dispatch.

3. **Sealed runtime limit omitted from execution: resolved.**
   - `cli/delivery_gateway.py:397-403` places the exact Charter value in v7 as `max_runtime_seconds`.
   - `cli/execution_contracts.py:197-207` requires a bounded positive v7 runtime field and rejects malformed or expanded envelope shapes.
   - `_execute_prepared_delivery` passes the value to the Magentic supervisor at `cli/delivery_gateway.py:911`.
   - Manager routes use `min(120, max_runtime_seconds)` at lines 1003-1012. Claude and Codex workers use `min(300, max_runtime_seconds)`, and Ollama uses `min(60, max_runtime_seconds)`, at lines 1033-1043.
   - Independent checks with a 45-second envelope observed 45 seconds at Claude manager, Codex manager, Claude worker, Codex worker, and Ollama. The preparation/supervisor test confirms the sealed 300-second value reaches Magentic unchanged.

### Requirement Fit

- The implementation preserves approved source bytes, role definitions, specialist capabilities, maximum instances, prohibited capabilities, provider grants, and enforceable limits across the Shaper-to-Delivery boundary.
- Atomic staging, generation fencing, v6 inspection-only compatibility, receipt linkage, and the live Magentic producer/verifier route match the approved Chunk 1 plan.
- The approved deferral of broad cross-runtime adapters, amendment epochs, nested subagents, and ordinary Chat MCP is respected.
- Commit messages use Conventional Commit prefixes and separate implementation, handback evidence, and session handoff.

### Validation Fit

- Independently reran 69 focused contract, lifecycle, compatibility, projection, gateway, provider-route, Magentic, and lifecycle tests; all passed.
- Reviewed the final full-suite evidence: **1,321 passed, 1 skipped**.
- `git diff --check` passes.
- Reviewed the source-binding mutation tests, unsupported-capability tests, read-only-as-editor denial, narrowed-limit projection tests, supervisor timeout assertion, and Claude/Codex/Ollama adapter timeout assertions.
- Reviewed the completed live v7 receipt for attempt `6ba14eb0b8dd4002a0392cb8f8ffc2c8`: it links the four authority digests, records a Claude edit and passing targeted test, includes completed Ollama calls, denies later producer proposals, and has no pending unknown action.

### Residual Risks

- Ollama proved functional but supplied weak and repetitive semantic verification; this affects efficiency and judgment quality, not Flow's authority or evidence integrity.
- SQLite migration history, default attempt selection, deletion evidence, and cumulative wall-clock budgeting remain explicit later-operability work.
- Security/privacy review found no acceptance blocker for this local slice: provider sends remain Flow-granted, worktree paths are bounded, diagnostic traces are private, and the reviewed receipt contains no credential material.
- UX is limited to CLI inspection and diagnostics; those surfaces are documented and deterministically covered.
