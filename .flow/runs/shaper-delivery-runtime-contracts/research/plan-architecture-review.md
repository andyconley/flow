# Planning architecture review

Recommended modules: `delivery_contracts.py`, `delivery_control.py`, `delivery_projection.py`, and `legacy_delivery.py`, with focused changes to `runstate.py`, `execution_contracts.py`, `execution_ledger.py`, `delivery_gateway.py`, the MAF runner, and CLI/docs.

The `run.json` replacement under a per-run lock is the lifecycle authority commit point. Immutable artifacts are staged before it; execution-ledger attempts are created later at dispatch. This avoids claiming impossible filesystem-plus-SQLite atomicity.

Protocol v7 links the sealed charter, logical delivery attempt, and owner generation to the existing execution machinery. V6 remains a preserved inspection format and never enters the new eligibility path.

Architect advisory expertise query `e7fe88bf-0169-40ca-86da-5ee1e7472b63` returned `no_match`; no advisory content was injected.
