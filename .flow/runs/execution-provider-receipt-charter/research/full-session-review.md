# Full review of supplied Flow conversations

- Date: 2026-09-19
- Status: source review complete; architectural conclusions remain draft requirements

## Coverage and source limits

- Read all 52 prompt positions in the shared [Flow Shapping conversation](https://chatgpt.com/share/6aaed767-428c-83ea-845c-6622dd4b6014), from the opening hooks/skills/subagents discussion through the Work-chat discussion. Some adjacent turns render together in the shared page; all positions were navigated.
- Read all 456 lines of `/Users/andyconley/.codex/attachments/e8a907b9-dbce-4be4-b4e2-be95c4c64ea6/pasted-text.txt` and all 103 lines of `/Users/andyconley/.codex/attachments/76222f30-37af-4c75-a181-5ad2e6afae34/pasted-text.txt`.
- Read the complete original September 9 `Software Engineer Overview` chat through the Codex app task history (11 turns). This provides direct evidence for the execution-kernel and artifact-store proposals that the first transcript only summarized.
- Read the complete original `Summarize Flow Architecture` chat through the Codex app task history (36 turns), beyond the 103-line pasted excerpt. Its later turns materially change the architecture discussion: routing, delegation budgets, and a Microsoft Agent Framework (MAF) reuse spike.
- Microsoft Agent Framework is an explicit candidate in the complete `Summarize Flow Architecture` chat. Microsoft Foundry Model Router is separate external research added after the user asked about the Microsoft router; do not conflate the two.

## User-confirmed direction in the shared chat

| Subject | Evidence | Interpretation |
| --- | --- | --- |
| Preserve the host interface | Prompts 3–4: Andy wants the harness beneath Codex and Claude rather than recreating UI, MCP, plugins, approvals, or exploratory chat. | Flow is a headless, durable control layer. |
| Delegate routine progress | Prompt 4 and prompts 33, 39–41: Andy wants formal kickoff, then stage management without repeated human approval; genuine exceptions return to Andy. | The charter must express delegation and escalation. Current approval gates may need a future authority change; the draft must not make perpetual engineer approval a product requirement. |
| Be frugal with paid models | Prompts 2, 9, 20–26: local models should handle suitable volume, but Andy explicitly rejects eliminating paid use and adding a third paid provider merely for novelty. | Cost, capability, risk, and validation matter. Local-first is a later routing behavior, not a synonym for low semantic tier. |
| Preserve existing Flow specialists | Prompts 26–29: Andy asks the assistant to inspect the actual 13 lifecycle roles and considers multiple independent instances. | Do not replace them with language-specific generic coding personas. |
| Distinguish Shaper and Delivery Lead | Prompts 30–41: Andy accepts Delivery Lead and then Shaper; Shaper challenges during ideation and represents the agreed vision afterward; Delivery Lead coordinates delivery but does not own product or architecture. | Define charter and authority early. Automate the roles later. |
| Consolidate and pressure-test | Prompts 45–49 and first attachment: Andy accepts consolidation and asks to compare it with the repository. | Existing lifecycle/orchestration is the foundation; the execution attempt/receipt is the first new seam. |

## Important assistant proposals and open status

- Prompts 10–12 propose Codex CLI in OSS mode as an agent **harness** using Ollama or LM Studio as a model runtime. That is different from a raw Ollama worker. The first contract must distinguish harness, inference provider, requested model/profile, and observed model; actual CLI support and flags need fresh verification in the solution lane.
- Prompts 13–18 propose CRAP, mutation testing, and risk-driven quality levels. Andy engaged with the examples, but no repository-wide quality policy or threshold was approved. The receipt should link declared validation to acceptance; specific CRAP/mutation gates belong to later project policy.
- Prompts 19–25 propose MCP, hooks, a Mac-hosted service, secure remote access, and cross-session supervisory handoff. These are later access/continuity designs, not prerequisites for a one-worker execution contract. Claims about current hosted-product capabilities may have drifted and need fresh documentation checks before design.
- Prompts 27–29 propose adaptive teams and per-assignment model choice. The one-worker slice should not implement topology or routing, but its identities and receipts must remain usable when those arrive.
- Prompt 39 describes `SHAPED → DELIVERY` and later reshaping triggers as an intended Shaper behavior. That does not itself create a new Flow lifecycle transition now.
- Prompt 41 explicitly says small scout work may skip Delivery Lead. That threshold remains open.
- The original September 9 chat proposes a queue/DAG, deterministic kernel, stop/retry/resume, commit-bound handoffs, and a separate artifact store. Andy explicitly requested that durable Flow artifacts live in a separate user-owned path that can be Git controlled and backed up off machine. Building the store before the execution kernel was the assistant's sequencing recommendation, not an explicit user decision. A later assistant comparison proposed the first worker path, while the later architecture chat proposed testing MAF before owning execution machinery.

## Corrections to the prior draft

1. Separate **agent harness/execution provider** from **model runtime/router**. The previous draft combined provider and underlying model too loosely.
2. Preserve the user's delegated-approval goal. Current `flow-define` requires Andy's approval of this definition, but a future Shaper may approve routine stage transitions within an explicit charter. The draft had overgeneralized the current gate.
3. Represent charter alignment state and the authorization event without implementing an automated Shaper or a new lifecycle lane in the first slice.
4. Require a bounded, blocked outcome when an unattended worker needs ungranted permissions; do not assume an interactive approval prompt can resolve it.
5. Trace observed validation results to the charter's acceptance criteria. The chat's CRAP/mutation examples illustrate the pattern, but do not mandate those tools here.
6. Treat user-controlled, Git-capable, off-machine-backup-ready artifact storage as a user-stated architectural requirement. Using `.flow/runs` for the first proof is only an unapproved temporary placement. The original chat also distinguishes durable artifacts from runtime checkpoints, cache, credentials, and transient process state.
7. Treat Microsoft's routing products as external options for later evaluation. They do not replace Flow's assignment authority, provider attempt record, or worktree/commit evidence.

## Remaining decision points

- Does the first Codex worker need to exercise a local model, or is a direct Codex model sufficient to prove the execution contract? The pressure-tested sequence says local routing follows the first worker path; the earlier discussion strongly values local use.
- What exact routine approvals may a Shaper perform under delegation, and which remain human-only? The current define lane's explicit engineer approval remains in force until that contract is changed.
- Is `.flow/runs` acceptable for the first proof while the user-controlled artifact location is designed, or must artifact topology be settled first?
- Before committing to a bespoke runner, compare a thin Flow policy/receipt layer over MAF with Flow-owned execution. Validate subscription-backed Claude and Codex paths, local models, capability boundaries, checkpoint ownership, and actual adapter effort in a spike. Chat claims about SDKs, licensing, or subscriptions are research leads, not verified current facts.

## Findings from the complete `Summarize Flow Architecture` chat

- Andy cites an actual 150-subagent run consuming about 10% of weekly tokens and later an 11-subagent follow-up after a best-effort release decision. The failure is unbounded work amplification. Charter budgets must include delegation count, concurrency, retries, resource use, confidence target, accepted risks, and an explicit stop condition; expansion requires Shaper approval. The numerical examples in the chat are examples, not global defaults.
- Andy asks to use an existing orchestration framework and avoid building excess machinery. The chat evolves from LiteLLM/Claude Code Router research to a proposal that MAF might own runtime orchestration/checkpoints while Flow keeps charter, policy, artifacts, evidence, archive, and memory. The last handoff asks for a bounded MAF spike against a known over-delegation failure. This conflicts with treating a bespoke Flow execution kernel as already selected.
- Subscription-backed Claude Code, Codex, and local models are the intended resources. The chat itself contains a corrected LiteLLM overclaim and uncertainty around Codex subscription integration. Treat all integration claims as hypotheses for a live compatibility check; do not design around OAuth impersonation or assume an API gateway preserves the native agent harness.
- The Shaper may live in ChatGPT or Claude chat and use an MCP-connected Flow service. Flow remains the durable authority for the charter and decisions. MCP is a proposed interface, not a requirement for the first receipt schema.
- The earlier Shaper Contract v1 and single-Codex-worker receipt were positively received. The later MAF reuse proposal is a design-direction update, not an instruction to throw away Flow's existing lifecycle, artifacts, or specialists.

## Overall interpretation

Define provider, receipt, and charter as implementation-neutral boundaries. Make storage topology, hard delegation controls, and MAF-vs-Flow execution ownership explicit decisions before a runner plan. The first vertical proof remains one worker handback, but its implementation should follow the reuse spike rather than presume a custom kernel.
