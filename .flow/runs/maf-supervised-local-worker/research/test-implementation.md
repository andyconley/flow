# Focused execution tests

`tests/test_execution.py` covers the Flow-owned execution boundary without
starting Microsoft Agent Framework or calling Ollama.

## Test oracle

| Behavior | Representative input | Observable result |
| --- | --- | --- |
| Contract binding | Child action with a changed model or action ID | Flow rejects it before a ledger decision or adapter call. |
| Result binding | Completed result with changed model, output hash, or evidence label | Flow rejects the result and does not seal it as a completion. |
| One-use grant | Consume the returned grant twice and repeat the request | Only the first consume starts the action; the replay is denied. |
| Run-wide limits | New attempts after three unknown or six completed actions | Existing actions in the same work ID enforce the concurrency or delegation cap; a new attempt does not reset either count. |
| Successful stub | Valid implementing run, valid child proposal, injected local stub | A completed receipt records `local-stub` and `physical_call: false`. |
| Duplicate proposal | Same valid proposal twice | The adapter executes once; the second proposal is denied. |
| Supervisor launch failure | Supervisor raises before proposing an action | A failed receipt contains no actions. |
| Adapter uncertainty | Adapter raises after grant consumption | Flow records `unknown` and does not retry. |
| Unsafe input | Missing run, invalid manifest, outside task, or unbound child action | Preparation or proposal fails before any adapter call. |
| Optional runtime boundary | CLI is imported with its execution call patched | The CLI returns the structured result without importing MAF. |
| Owner-only storage | Prepare an execution attempt and seal a launch-failure receipt | Execution/checkpoint directories are `0700`; ledger, envelope, and receipt are `0600`. |
| Local-only HTTP | Local Ollama route with proxy environment variables present | The opener disables proxies and rejects redirects without sending a network request. |
| Grant expiry | A grant issued more than 60 seconds ago | Flow denies it before recording a worker dispatch. |
| Checkpoint receipt | A completed action with a missing checkpoint file | Flow seals a failed receipt rather than accepting the checkpoint ID. |
| Parent-child protocol | Wrong version or attempt, malformed/oversized JSON, premature finish, EOF/crash, or a second proposal | The supervisor rejects the child before an unsafe terminal result is accepted. |

The fixture copies the run shape into a temporary repository, patches the
effective specialist definition, and gives the selected assignment a local
Ollama declaration. Injecting an adapter causes the gateway to relabel the
envelope `local-stub`; therefore the automated suite cannot be confused with
a physical Ollama result.

## Evidence

```
/opt/homebrew/bin/python3.12 -m unittest tests/test_execution.py tests/test_maf_supervisor.py -v
Ran 24 tests ... OK

/opt/homebrew/bin/python3.12 -m py_compile tests/test_execution.py
git diff --check -- tests/test_execution.py
```

No test performed a paid-model request, an Ollama request, or a MAF child
launch. The local HTTP check replaces the opener with a test double and proves
its proxy and redirect controls only. The separate acceptance smoke remains
the only evidence for physical Ollama behavior.
