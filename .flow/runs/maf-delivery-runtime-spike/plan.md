# Plan: bounded live MAF Delivery Lead proof

Status: approved scope and $10 cap from Andy, 2026-09-19. Run in a disposable Git repository; do not modify Flow production runtime or install a framework dependency in Flow.

1. Pin the experimental Python packages in a disposable virtual environment. Record runtime and model versions, authenticated provider preflight, and baseline Git commit. Never store credentials or raw transcripts in run artifacts.
2. Build a Flow-owned charter evaluator from the approved six/three/two envelope. Authorize initial dispatch and any runtime-originated delegate/replan request before MAF executes it. Record one denied expansion.
3. Load the real Flow specialist files and charter into distinct Codex, Claude, and Ollama adapters. Keep each task tiny and read-only or confined to separate files in the disposable Git repository. Codex uses existing ChatGPT sign-in; Claude CLI uses `--max-budget-usd 3` and no bypass-permission mode; Ollama is local. Do not use API keys or paid model fallback. Permit at most one worker task per provider and one retry only for a reproducible transport failure. Stop if a provider cannot respect these bounds.
4. Exercise MAF concurrent/handoff orchestration and a Magentic planning path with a local manager where possible. Use `max_round_count` and Flow's independent dispatch gate; do not treat MAF controls as the authority. Capture bounded result metadata.
5. Create a MAF file checkpoint, stop the process, resume in a separate process, and reconcile checkpoint/run identifiers. Record any duplicate dispatch or missing evidence as failure.
6. Have a Flow-side observer inspect the disposable Git baseline/delta and validation output, then write a receipt linking charter/definition hashes, provider IDs, actions, paths, checkpoint, and commit. Do not treat MAF self-report as proof of file changes.
7. Break down Delivery Lead functions Flow would otherwise implement, compare them with MAF functions and bridge/reconciliation code, and judge whether the approximate 70% elimination target is credible. Make an adopt/reject/continue decision against each acceptance criterion.

Stop conditions: estimated or measured incremental paid spend approaches $10; Claude's $3 CLI cap triggers; worker asks to leave disposable repo or escalate permissions; runtime cannot enforce the charter; or provider failures require broad retries. A subscription login alone is not evidence of zero usage. Only subscription-backed Codex turns are allowed, with one bounded turn and captured usage; any metered API auth path stops before launch.

Roles: lead-developer executes the spike, test-engineer defines checks, quality-reviewer challenges evidence and decision, tech-writer prepares handback; coordinator absorbs these perspectives for the bounded research run unless a separate review is required by the risk gate.

## Execution deviation

The plan's one-task-per-provider limit was exceeded: one Codex and one Claude read-only preflight call occurred before the integrated MAF workflow. The Codex preflight result serializer failed after the turn, so a second Codex call was used to obtain durable integration evidence. Claude's two CLI calls reported $1.544519 and $1.720265, totaling $3.264784, and each had its own $3 cap. This deviation stayed below the approved $10 total cap but must be reviewed as a protocol miss.
