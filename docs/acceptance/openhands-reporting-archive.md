# OpenHands usage and archive repair acceptance

Base: released v0.44.0, `7d0f1b6020a436e3c24c986450cb9570da0251f2`.
Tests use temporary projects and the pinned SDK 1.54.0. They do not invoke live
native providers, change profiles/authentication, or modify Witmark.

The existing committed Ollama64K, Codex-native and Claude-native acceptance
fixtures were inspected for their token/cache semantics and missing pricing
and timestamp data. Their original artifacts remain unchanged.

## Reproduction on the released code

`FLOW_USAGE_BASELINE_CLI=<v0.44.0 checkout>/cli <pinned-python>
tests/openhands_usage_eval.py` executes two real SDK parents in fresh processes,
with one delegate each, against a loopback synthetic endpoint.

Six measured requests consume 500 prompt tokens. The released parent's cumulative
projection reports only 450: the new child's `task_00000001` bucket replaces the
historical child's 50 tokens. Both child SDK histories remain on disk.

## Repaired deterministic SDK lifecycle

`<pinned-python> tests/openhands_usage_eval.py` executes five fresh parent
processes, including same-session continuation, a new session, interruption and
failure after metered inference. Thirteen requests produce these combined totals:

| Model | Calls | Fresh input | Output |
| --- | ---: | ---: | ---: |
| openai/parent | 8 | 800 | 160 |
| openai/child | 5 | 250 | 100 |

Distinct task UUID buckets survive the restarted parent. SDK parent/child token
sums match endpoint request measurements exactly. Reimport adds zero calls;
normalization has zero stale rows. The prior session remains referenced, elapsed
seconds accumulate, and failure/interruption projections retain spent usage.
Summary, trend and active read the imported SDK data. Actual CLI harvest,
summary and active commands also pass with an isolated reporting HOME. The synthetic endpoint is
accounting/lifecycle evidence, not a model-quality or live-provider benchmark.

`tests/openhands_routing_resume_eval.py` independently passes real SDK routing,
waiting/confirmation inspection and continuation across fresh processes.

## Archive and SQLite integration

`tests/test_openhands_usage.py` covers native-transcript precedence by exact
session identity, both import orders, parent/child rollup exclusion, resume,
reimport, new sessions, pricing provenance, raw correction and projection fallback.

`tests/test_openhands_workflow.py` runs the approved full lifecycle, verifies
sealed artifact digests and events, generates a searchable abstract after a real FTS5 probe in a temporary home through the
archive service, and retries after an injected enrichment failure. Retry does not
change canonical run/event/summary/abstract bytes or approve changed dispositions.
