# Review: multi-turn Magentic Flow controls

## Review Summary

**Verdict:** APPROVE the bounded research result. This is not approval of production integration or MAF adoption.

**Overview:** An independent rerun produced two distinct Flow request IDs, replayed the second from a checkpoint without another ledger dispatch, rejected raw participant injection through the run-local builder, and denied Magentic's third replan. The receipt now labels the deterministic work `local-stub`.

### Critical Issues

- None within the local research scope.

### Important Issues

- None within this run's deterministic, local research scope. The remaining work below must be resolved before production use.

### Suggestions

- [`acceptance-criteria.md:3`](acceptance-criteria.md): Say "two completed stub dispatches" to match the receipt. The current validation results state this clearly, and the machine-readable provider field is now `local-stub`.
- [`multiturn_probe.py:102`](multiturn_probe.py): `replan_count` exists only on the manager object. Test a separate-process checkpoint resume and bind replan identity to durable state before using this for real work. A restored manager may reject an allowed replan as a duplicate; this run does not prove restart semantics for replans.
- [`multiturn_probe.py:112`](multiturn_probe.py): The builder rejects raw participants passed through this function, but code can still instantiate `MagenticBuilder` directly. Production integration needs one enforced construction path and a test that all execution entrypoints use it.
- [`multiturn_probe.py:19`](multiturn_probe.py): The charter digest is derived from a module constant, not an authoritative Flow charter supplied to the builder. Bind and verify the actual charter at integration time.

### What's Done Well

- `WorkflowContext` checkpoint state provides a stable sequence in this tested replay path. The duplicate request raises and halts the workflow, closing the earlier failure in which a bounded denial response allowed later work.
- The replan test exercises MAF's stall path into `manager.replan`; the SQLite ledger shows two completed replans and the third denied before any specialist dispatch in that scenario.
- The run documents its prototype scope and explicitly disclaims global construction enforcement, live provider behavior, and an adoption decision. No paid provider code is invoked.

### Verification Story

- Tests reviewed: I independently ran `multiturn_probe.py` in the disposable MAF environment with fresh temporary roots before and after the provider-label fix; both exited 0 and reproduced the key IDs, duplicate denial, and replan cap. I inspected the updated `receipt.json` and implementation.
- Build/runtime checks reviewed: The probe uses the installed MAF workflow and `FileCheckpointStorage`; its replay is a fresh builder in the same process. I did not run a separate-process restart or contact Ollama or a paid provider.
- Remaining risks: The ledger records stub calls, not physical provider requests. The checkpoint and replan tests use deterministic managers and one specialist. No production code or commit changed, so Conventional Commit review does not apply. The artifacts follow the run directory structure and are readable.
