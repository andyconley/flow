# Validation results: Minimal capability spike

- Date: 2026-09-19
- Target: [SDK inventory](research/spike/sdk_inventory.py), [MAF stub](research/spike/maf_stub.py), [preflight](research/spike/preflight_evidence.py), and [report](research/reuse-spike.md)

| Check | Result | Transfer limit |
| --- | --- | --- |
| Disposable environment/package install | Passed with approved network access; `openai-codex` 0.154.0, bundled CLI 0.154.0, MAF core 1.19.0, Python 3.12.13. The first sandboxed install was DNS-blocked. | Confirms these public packages, not their operational integration with this user's subscription. |
| SDK public interface inventory | Passed; captured workdir/sandbox/approval, thread ID/start/resume, turn stream/result, interrupt. No SDK client or worker turn constructed. | Interface shape only; effective grants and event delivery remain unverified. |
| MAF stub | Passed; one pending request, two checkpoints, restore into new workflow instance, denied response, terminal output; no model call. | Same-process restore only, not process restart or Codex recovery. |
| Independent repeat | Passed after selecting the pending-request checkpoint by state rather than list position. Two same-environment reruns matched output; a second fresh pinned virtual environment matched all three JSON outputs byte-for-byte. | Package versions are pinned for reproduction; future releases may differ. |
| Mutation check | Ran: changed the policy action in a temporary copy from `write_source` to allowed `read_report`; the `denied` assertion failed as expected (exit 1). Original script remained intact and passed again. | Checks this simulated fail-closed policy assertion, not production authorization. |
| Scope and hygiene | `git diff --check` and Flow dispatch validation passed. Only run-local spike/handback artifacts were changed; no production package metadata, CLI runner, worktree, or model prompt was used. | File inspection cannot prove hidden runtime behavior; no real worker was launched by these scripts. |

One early MAF rerun failed because checkpoint listing order was assumed. The script now selects the checkpoint with `pending_request_info_events`; this failure and fix are described in [reuse-spike.md](research/reuse-spike.md). No repo-wide suite or deployment was run because this investigative spike changes no production code.
