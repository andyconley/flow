> Update: the read-only production ACP task now passes with the explicit local GPT-OSS configuration. See [NATIVE-ACP-RESULTS.md](NATIVE-ACP-RESULTS.md) for evidence and limits. The historical failures below are retained.

# Native ACP verification: not ready for release

The continued test found and repaired actual wiring defects. However, **a complete
production ACP/provider knowledge-use task has not passed** under the retained
local-model/no-credential constraint. Do not merge/release based on the earlier
MCP-only success.

Verified fixes:

- Installed/configured knowledge now blocks agent submission when its runtime,
  audited snapshot or pinned dependencies are missing. No substitute search runs.
- ACP clients start inherited MCP commands with a filtered environment. The new
  absolute `knowledge_runtime/stdio.py KNOWLEDGE_HOME` launcher sets its own module
  path and does not depend on inherited custom environment variables.
- Native worker sandbox grants read-only knowledge/code/cache access. Query
  writes use native per-run scratch; native tools cannot trigger enrichment or
  write maintained notes. Flow's supervisor reconciles changes every five seconds.
- A real sandboxed MCP client with custom environment removed started that exact
  launcher and retrieved the expected authored support-lead card. See
  `evidence/native-mcp-clean-env.log`.
- PID/group identity is persisted before process observation. Observation failure
  stops the initial owned group and remains explicitly uncertain for detached
  descendants. Provider descendants are stopped after root exit and re-observed.
- Credential-free Codex local-model config gets its own loopback-only sandbox;
  the common Claude profile is preserved. Flow's supported Ollama coordinator can
  use the configured loopback endpoint without changing active services.

## Actual task attempts and blocker

All attempts used copied local binaries, task-local homes/workspaces and no
`auth.json` or paid API. The first outer OS sandbox prevented supervisor `ps`;
its uncertain launch was checked before another run. Later native worker profiles
kept the actual provider offline while the supervisor retained process visibility.
Every stopped/failed scope was reconciled by recorded process identities.

The copied Codex CLI 0.163.0 and codex-acp 2.2.2 successfully established a local
provider session. Qwen2.5 rejected ACP's thinking request. Qwen3 accepted the
request but did not make the required knowledge calls. The actual local request
catalog contains the managed tools under the `mcp__python` **namespace**:
`knowledge_status`, `search_cards`, `traverse_cards`. This is captured in
`evidence/local-acp-tool-catalog.jsonl` without prompts or corpus data. The local
model nevertheless reported those callable functions unavailable and returned no
valid required result. That is a provider/model tool-use compatibility blocker,
not proof the tools were executed. A small flat-versus-namespace synthetic probe
also failed its flat control at its short output budget, so it does **not** isolate
namespace handling as the sole cause.

Using ACP as the Goose coordinator also cannot supply ordinary platform Summon
tools: the upstream ACP provider ignores its ordinary `_tools` argument. Flow's
supported local Ollama coordinator reached the real knowledge-status tool, but
that small-model run did not delegate or return the required task result. Its
workflow correctly ended blocked. No successful search/graph result or artifact
use was fabricated from these failures.

`verify_acp.py` retains the bounded real implementation/check/review harness;
`verify_acp_read.py` retains the smaller actual Flow native-provider task. The
latter's captured result in `evidence/acp-read-failed.json` explicitly has
`passed: false`, no search/graph calls, no verified source quotes and no workspace
writes. The earlier 15-query, graph and direct MCP results remain valid for those
narrower paths; they do not certify native task completion.

Remaining acceptance gate: a supported local ACP/model combination must invoke
both managed tools, return the expected authored text and real graph neighbor,
and pass the task's independent checks through Flow. Alternatively the user would
need to authorize a suitable existing signed-in provider test; the original
no-credentials/no-paid-API constraint was not bypassed. No such authorization or
external-provider execution occurred in this continuation.

## Distribution and provisioning checks

Eight additional checks passed, including real anonymous Git transport against a
loopback-only synthetic repository; resolved commit receipts; independent corpus
update preserving local edits/deletions and runtime version; missing-ref failure;
real managed fresh-install seeding with verified release fixtures; explicit
unprovisioned/missing-dependency refusal; read-only status behavior; and failed
offline setup/missing local model preserving authored notes and allowing export.
The fresh-install fixture runs the actual installation/control/seed code and
creates a real isolated interpreter. Wheel/npm commands are explicitly stubbed;
it is not a claim of a fresh full dependency installation. A separate empty-
wheelhouse test really invokes offline pip and verifies its failure.

Failed setup retains its partial `runtime/` directory for inspection and refuses
replacement. Recover by inspecting/removing only that failed virtual environment,
or provision another isolated environment and configure its Python explicitly.
Never remove the maintained `notes/`, backups or exports to repair dependencies.

Final post-rebase suite: 187 tests passed. The final sandboxed native BM/direct-MCP replay also passed all 15 search requests, role filtering, graph and snapshot integrity checks. These are narrower successes; the native provider task gate above remains blocked. All live attempts and the temporary proxy/model server are stopped. No action remains in an uncertain execution state, and no automatic-approval denial was bypassed.
