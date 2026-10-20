# Workflow ownership and approvals

The native host is the conversation/approval surface. Goose coordinates all
research, definition, solution, planning, implementation and specialist dispatch.
LangGraph owns stage transitions, execution intents, checkpoints and recovery.
The host never substitutes its own research, synthesis, plan or worker delegation.

1. `create` snapshots project context and records the request without inference.
2. `assign --stage STAGE --question QUESTION` proposes a versioned stage assignment.
3. Human authorization names the exact assignment revision through `run-stage`.
4. The graph binds workspace/context/authorization, records an uncertain intent,
   and invokes the Goose coordinator. Goose chooses converted roles/providers.
5. A completed stage publishes substantive content with runtime provenance.
   A planning result may propose a complete brief; that brief remains unapproved.
6. The host presents results/questions and records human stage decisions. Stage
   approval is never implementation approval. Research that changes the project
   candidate is preserved but blocked for scope review.
7. Exact brief approval starts graph-owned implementation, independent checks,
   fresh review and closure. Human acceptance and deployment remain separate.

Each authorized stage has a bounded budget. Missing/changed assignment identity
or actor refuses dispatch. A restart reuses a completed result; uncertain effects
interrupt for evidence-backed reconciliation before replay. Permission/scope
failures return to the human without implicit retry or host fallback. Imported
historical checkpoints remain readable but cannot authorize new work.

User-supplied context/notes can be recorded directly, but host-generated research
is not a substitute for the coordinator. Optional stages can be omitted when the
human already supplies the needed decisions/brief; this does not transfer
coordination ownership to the host. No runtime artifact grants approval itself.
