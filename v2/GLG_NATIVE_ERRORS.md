# Flow v2 native permission and scope error propagation

The support-export exercise exposed a real loss of error provenance. Codex's standard command renderer discarded command output from the final result, leaving a generic failed tool. Goose's parent then received a generic failed delegate and could dispatch another worker instead of pausing at the permission boundary.

The isolated integration now preserves an explicit structured boundary error:

1. The generated Codex ACP wrapper retains command diagnostics. For a nonzero command with the observed Python `PermissionError: [Errno 1|13] Operation not permitted|Permission denied` diagnostic, it emits kind, errno/code, original message/output and source in `goose.native.boundary`. Zero-exit output and ordinary error prose do not become permission errors.
2. The isolated Goose ACP provider propagates that explicit record, or an actual rejected ACP permission decision, as a versioned `GLG_NATIVE_BOUNDARY` error. Explicit `scope_required` records use the same path. It stops the native stream and cancellation is sent to the native client.
3. Goose's foreground subagent operation treats that record as a coordinator error, before delivering a generic failed-delegate result back to the parent's model. It cannot dispatch another worker around that denial.
4. GLG decodes the typed record only from an error event/error channel, preserving the original diagnostic in the job/result record. It returns `permission_required` or `scope_required` to the existing graph's immediate interrupt. Cached denied operations retain that outcome and do not resubmit. Explicit actor/reason resume is still required before a new authorized attempt.

No missing telemetry, generic nonzero exit, ordinary test failure, or assistant prose is inferred to be a permission failure. Unstructured failures remain unstructured; their cause is not guessed. This fixes the observed Codex command diagnostic path and explicit ACP/typed permission or scope errors, not every possible future provider error vocabulary.

## Verification

- Four focused Rust tests pass: original explicit error retention, negative classification, actual ACP transport error-before-terminal plus cancellation, and parent dispatch stopping on the structured failure.
- Three focused Python test methods pass: execute the actual generated renderer body against denial/non-denial cases; decode explicit permission/scope records without classifying assistant prose or missing telemetry; pass the real job adapter through SQLite-backed lifecycle approval into the graph's immediate pause with one subprocess dispatch and no dispatch on ordinary resume/cache reuse.
- Full Python regression suite: 67 passed. Cargo format and the isolated Goose CLI build passed. No new provider calls, global installs, credentials or production changes were used.

Original end-to-end evidence and its blocked closure remain unchanged. The earlier observed propagation gap is historical evidence; this follow-up closes that specific gap with focused regression coverage rather than relabelling the old run as a clean permission-pause result.
