# Native retained local agents

A sealed `local_agent_profile` selects retained MAF/Ollama participants for a native v9 chartered job. Flow still owns authority, provider selection, scoped effects, receipts, checkpoints and lifecycle transitions. The profile adopts the successful local-agent POC's execution behavior; it does not call the older one-shot whole-file JSON editor.

## Development execution

Use the development CLI and a verified optional MAF interpreter. This does not replace the installed Flow release:

```bash
export FLOW_MAF_PYTHON=/absolute/path/to/verified/project-runtime/bin/python
/opt/homebrew/bin/python3.12 cli/flow.py run execute-chartered-job WORK_ID \
  --project-root /absolute/path/to/project \
  --worktree /absolute/path/to/approved-isolated-worktree \
  --source-commit APPROVED_SOURCE_COMMIT --json
```

The work item must already have approved native requirements, Shaper Intent, orchestration and job charter. Include `local_agent_profile` in the approved intent before execution; Flow resolves its defaults and carries the canonical profile into sealed authority. Changing approved profile or assignment authority requires the native amendment path. Do not edit saved run state directly.

The optional runtime pins MAF core 1.20.0, orchestrations 1.3.0, the Ollama agent extension 1.0.0b261002 and Ollama Python client 0.5.3. The hashed lock records the full tested dependency closure. Flow's ordinary CLI remains standard-library based; readiness probes use the optional interpreter. Development verification used a project-scoped runtime and did not replace the installed release.

## Profile and accounting

The default profile resolves to:

```json
{
  "context_tokens": 49152,
  "output_tokens": 12288,
  "context_reserve": 2048,
  "request_timeout_seconds": 600,
  "turn_timeout_seconds": 2400,
  "manager_calls": null,
  "manager_rounds": null,
  "delegations": null,
  "replans": null,
  "tool_calls": null,
  "max_stall_count": 2
}
```

These are configurable execution controls, not additional user requirements. A null count removes that profile's count ceiling. Legacy contracts retain their existing limits and receipt semantics. The SDK requires a positive iteration integer: the native participant uses `sys.maxsize` to represent effectively uncapped iterations, bounded by elapsed time, context and pressure guards. The SDK accepts `max_function_calls=None`.

The verification model remains `gemma4-26b-dev:latest`; profile approval does not authorize a model change. Actual Ollama requests bind `num_ctx=49152`, `num_predict=12288`, temperature 0, seed 42 and `think=false`. Context checks reserve output and input headroom before a send; retained sessions also use observed prompt usage and request growth. Configured context size and retained client history do not independently prove backend cache retention or unlimited conversation capacity.

A specialist delegation can contain multiple model sends and tool actions. Observations distinguish `model_request`, `model_send`, `model_response`, model errors and tool results; count actual sends and responses separately. A request without a response is not successful inference. Provider selection is explicitly local for this profile; a non-Ollama binding is rejected rather than silently falling back to a hosted provider.

## Tools, histories and completion

Each assignment has its own retained native MAF session and tools. Other specialists' transcript broadcasts are not replayed into that history. Native manager requests carry a typed phase, conversation and authority packet. The HTTP transport preserves actual message roles and contents, rather than nesting the conversation as a JSON string inside a user message. Only the progress phase requests the structured progress schema; other manager phases use ordinary responses. Compact task packets carry assignment intent, authorized scope and current source hashes; scoped reads supply actual source content.

Producers can read files, write authorized UTF-8 source (including authorized new files), run the Flow-approved test command, submit a handoff and read preceding handoffs. Reviewers can read and run tests, then submit review findings; they have no write authority. The model cannot replace the declared test command with an arbitrary shell command. Flow checks live authority and assignment scopes around effects. The write tool accepts a nullable `expected_sha256`, matching the SDK's real argument binding. A null value does not bypass stale-source protection: Flow still requires the producer's current read hash and performs a compare-and-swap check before replacement. Explicit expected hashes are checked against the current source as well.

Producers may iterate and repair test failures. Testing before every edit is not mandatory. A source write is an observation, not completion of the whole job. Sequential producers use persisted handoff artifacts containing source hashes; the consumer must read its producer dependencies before integration writes. Stale handoff reads are invalidated after relevant edits.

Test evidence binds the source digest before and after the actual command; changed sources make that evidence stale. Review requires observed reads of every current source file and tests at the current digest. A passing review requires actual passing tests. Every write invalidates stored tests and review approval, including another specialist's approval. Native handback and acceptance still require genuine output artifacts and valid receipts.

## Pressure and recovery

See [local-agent-resources.md](local-agent-resources.md) for telemetry and thresholds. The monitor reads actual kernel normal/warning/critical pressure, raw VM counters and rates, swap usage, GPU residency and service responsiveness. Low availability percentage alone is diagnostic. Critical pressure or allocation errors stop immediately. Sustained warning must coincide with continuing swapping or responsiveness loss to stop; monitor stop aborts the active socket and blocks subsequent work.

Development tests observed a pressure stop while a full regression workload overlapped local inference. This is evidence about the combined host workload, not proof of a model-only capacity limit. No thresholds were relaxed to force the trial through.

During stage 8 retry 1, the SDK rejected 21 attempted writes before they reached the parent because the optional expected-hash argument did not accept null. All 46 HTTP responses matched their requests; the candidate remained at eight passing checks and one failing check. This was not evidence that the model never attempted to write. The nullable binding was corrected while preserving stale-source checks; a clean retry 2 is in progress. Manager transport fidelity was also corrected, so its individual causal contribution has not been isolated experimentally.

Inspect persisted action/send evidence before recovery. An uncertain response is not automatically replayed. The normal recovery command resumes only a clean completed-action boundary:

```bash
/opt/homebrew/bin/python3.12 cli/flow.py run resume-chartered-job WORK_ID ATTEMPT_ID \
  --project-root /absolute/path/to/project --json
```

A strict local-manager context refusal can complete through the normal recovery path only when the protected parent trace proves zero provider I/O for that refused request, the refusal is bound to the sealed context allowance, and all required current worker receipts prove completion. Recovery preserves the pre-send refusal and records normal completion without replaying provider work or inventing a model response. An unknown worker response does not meet that condition: it still requires explicit reconciliation or abandonment.

Checkpoint restoration does not claim crash-restoration of a live specialist's conversation. Observed file-backed handoffs can be restored with their source binding; current-session reads and tests must be observed again. For a stopped uncertain request, reconcile or abandon the uncertain action through native commands before a separately authorized clean checkpoint continuation. Unload only the trial-owned model and wait for observed normal pressure before continuation; do not alter global OS or security settings.

## Verification status

Fresh implementation progression, sequential handoff and final regression verification are tracked in `.flow/runs/poc-local-agent-adoption-20261007/`. Final counts and completion status belong to the terminal evidence there. Earlier POC results are implementation reference material, not fresh proof of this integration.
