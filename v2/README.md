# Flow v2

Goose/LangGraph owns coordination and specialist dispatch across all stages.
The native host handles conversation and explicit human approvals.

Normal installation is the published, verified managed release. See the
[root guide](../README.md) and [installation/migration guide](FLOW_V2_INSTALL.md).
`flow` and `flow-v2` select the same managed runtime. There is no supported
source-bound/legacy installation mode or local Rust requirement for users.

Stage execution uses `assign` followed by human-authorized `run-stage` with the
exact assignment revision. Stage output and implementation approval are separate.
See [workflow contracts](GLG_WORKFLOWS.md), [operations](FLOW_V2_OPERATIONS.md)
and [native worker repairs](FLOW_V2_SMOKE_REPAIRS.md).
