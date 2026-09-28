# Acceptance Criteria

1. `approve-review-amendment` is legal only as protocol-revision-2 `reviewing -> reviewing`.
2. Original manifest bytes/path/digest remain unchanged; a separate content-addressed replacement, disposition artifact, and digest-chained amendment record are approved atomically.
3. Only verification corrections and appended read-only run-local reviewers are allowed; authority-expanding deltas fail closed.
4. Replay is idempotent and invalid state, stale/conflicting request, unsafe path, symlink, malformed schema, or tampering writes no lifecycle state/event.
5. Review dispatch and acceptance validate the effective manifest; Delivery evidence remains bound to the original.
6. Dispositions bind criterion id, decision, rationale, and evidence to the original acceptance-criteria digest; deferred decisions cannot satisfy acceptance.
7. Existing runs without amendments remain compatible, and acceptance binds amendment/replacement/disposition digests.
8. The MAF run records the approved AC2 v0.38 exception and AC13 named-baseline/no-new-regression disposition.
9. ADR 0020, installation-time wording, unsupported-host marker, and bug-planning guidance match actual behavior.
10. Focused lifecycle/orchestration/tamper tests and fresh quality, test, security, and SRE review pass before the MAF run accepts and archives.

