# Reuse spike: Codex SDK capability and MAF stub

- Date: 2026-09-19
- Scope: [approved narrow plan](../plan.md)
- Decision: **keep Flow as the first execution coordinator; defer MAF adoption**. This selects the smallest **next live test**, not a proven production runner.
- Environment: macOS arm64; Python 3.12.13 in `/private/tmp/flow-reuse-spike-20260919`; `openai-codex` 0.154.0; `openai-codex-cli-bin` 0.154.0; `agent-framework-core` 1.19.0. No Flow production dependency was changed.

## Reproduce

```sh
SPIKE_VENV=$(mktemp -d /private/tmp/flow-reuse-spike-XXXXXX)
/opt/homebrew/bin/python3.12 -m venv "$SPIKE_VENV"
"$SPIKE_VENV/bin/python" -m pip install --no-input openai-codex==0.154.0 openai-codex-cli-bin==0.154.0 agent-framework-core==1.19.0
"$SPIKE_VENV/bin/python" .flow/runs/execution-provider-receipt-charter/research/spike/preflight_evidence.py
"$SPIKE_VENV/bin/python" .flow/runs/execution-provider-receipt-charter/research/spike/sdk_inventory.py
"$SPIKE_VENV/bin/python" .flow/runs/execution-provider-receipt-charter/research/spike/maf_stub.py
```

The actual first successful install used unpinned `openai-codex agent-framework-core` in a fresh `/private/tmp/flow-reuse-spike-20260919` environment; the command above pins the versions it resolved for reproduction in a **new** environment. The first installation attempt failed in the sandbox because the package index hostname could not resolve. It succeeded through the approved network access path. Both packages were absent from the default `python3` environment beforehand. The scripts print bounded JSON without account identifiers, credentials, environment dumps, or model output. Captured outputs: [preflight](spike/preflight.json), [SDK inventory](spike/sdk-inventory.json), and [MAF stub result](spike/maf-result.json). Source: [preflight script](spike/preflight_evidence.py), [SDK inventory script](spike/sdk_inventory.py), [MAF stub script](spike/maf_stub.py).

## Observed

| Question | Observation | Evidence limit |
| --- | --- | --- |
| Codex SDK interface | Public signatures expose `cwd`, sandbox, approval mode, thread start/resume, thread ID, turn event stream, turn result (`id`, `status`, `error`, `items`, `usage`), and interrupt. | Import and signature inspection only; no Codex client or turn was constructed. [Inventory](spike/sdk-inventory.json). |
| Subscription status | The installed Codex CLI's read-only `codex login status` reported ChatGPT sign-in. | This does **not** prove the separately installed SDK can execute under that sign-in or that an unattended worker has the intended grants. [Sanitized preflight](spike/preflight.json). |
| MAF request flow | One stub entered a pending request; Flow-side simulated policy denied an action outside the charter; MAF carried `denied` to the result. | Policy is a pure stub, not production delegated-approval enforcement. [Result](spike/maf-result.json). |
| MAF checkpoint | File checkpoint storage recorded two checkpoints; a new workflow instance restored the checkpoint containing the pending request and emitted a terminal output with the denial. | Restoration happened in the same process; process restart and Codex worker recovery were not tested. [Result](spike/maf-result.json). |
| MAF Codex integration | No `CodexAgent`, `CodexClient`, or `openai_codex` reference was found in 84 Python files in the installed `agent_framework` core package. | This says only that the inspected **core package** lacks such a named integration; separate packages or later versions remain unverified. [Sanitized preflight](spike/preflight.json). |

The stub's final MAF status is idle with an output and no pending request. The report calls that **terminal output**, not a distinct `completed` workflow state. No model call occurred.

A repeat run caught an incorrect checkpoint-selection assumption: `list_checkpoints()` order did not reliably put the pending-request checkpoint last. The stub now selects by `pending_request_info_events`; two subsequent runs produced identical bounded output. This is a concrete reason to use checkpoint state/lineage rather than list position when later designing recovery.

The pinned commands also ran in a second fresh virtual environment; its preflight, SDK inventory, and MAF output matched the captured JSON byte-for-byte.

## Effort comparison

| Concern | Flow coordinator + Codex SDK | MAF wrapper + Codex SDK |
| --- | --- | --- |
| First worker adapter | Codex SDK adapter | Codex SDK adapter plus MAF executor bridge |
| Policy authority | Flow's existing manifest/lifecycle gates plus a new charter evaluator | Same Flow evaluator; MAF request events do not grant authority |
| Receipt trust | New Flow-side independent observer and linked receipt | Same observer and receipt; MAF output is not independent Git evidence |
| Persisted state | Flow run artifacts; runtime state still needs design | Flow run artifacts **and** MAF checkpoints; reconciliation needed |
| Dependencies | `openai-codex` if the live probe succeeds | `openai-codex` plus MAF core and its checkpoint format |
| Later recovery | Flow would own it | MAF provides a checkpoint primitive, but Codex recovery and Flow/MAF reconciliation remain unproven |

MAF's stub proves its request and checkpoint mechanism is usable. For the first worker it does not remove the Codex adapter, Flow policy evaluator, or independent receipt observer, and it adds another state store. On observed integration effort, **keep the direct Flow boundary for the next probe**. Reconsider MAF if a later multi-worker or recovery requirement shows it removes more work than the bridge and reconciliation add. No numerical line-count threshold was used.

## Unverified and next test

- Subscription-backed **SDK** execution, effective sandbox and approval behavior, real session/turn events, interruption, a real worktree, commit-bound handback, and independently observed receipt integrity remain unverified.
- The smallest live follow-up is one disposable-repository Codex SDK worker under the existing ChatGPT sign-in, one isolated worktree, a constrained change, and a Flow-side observer comparing baseline, changed paths, validation, and resulting commit. A separate MAF/Codex live probe is warranted only if this direct path exposes a recovery or coordination gap that MAF could close.
- A production delegated-approval authority matrix and gate change remain in the later policy slice; this stub demonstrates a denial boundary only.

## Claim and source boundaries

These findings use installed package observations and local stub output. Current official documentation describes the [Codex Python SDK](https://developers.openai.com/es-419/docs/codex-sdk), [Codex authentication](https://developers.openai.com/es-419/docs/auth), [MAF workflow HITL](https://learn.microsoft.com/en-us/agent-framework/workflows/human-in-the-loop), and [MAF checkpoints](https://learn.microsoft.com/en-us/agent-framework/workflows/checkpoints). Documentation supports the API interpretation but does not upgrade an unrun worker path to observed behavior.
