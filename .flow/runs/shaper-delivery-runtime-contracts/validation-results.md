# Validation Results

## Deterministic implementation checks

- Focused contract, lifecycle, compatibility, gateway, recovery, and Magentic suite: 87 tests passed before the final approval-boundary correction.
- Approval-boundary lifecycle suite: 12 tests passed after requiring and digest-binding `shaper_intent` at `approve-definition`.
- Independent quality re-review: APPROVE; 42 focused tests passed and `git diff --check` passed.
- Full implementation suite after all corrections: 1,316 tests passed, 1 skipped, in 131.079 seconds.
- Orchestration dispatch validation: passed with no findings.
- Data review: acceptable for the v7 handback; durable SQLite migration history remains a nonblocking follow-up.

## Mutation check

The `start-plan` comparison between the approved Shaper-intent digest and current bytes was deliberately inverted. `DeliveryControlTests.test_start_plan_is_atomic_idempotent_and_binds_authority` failed with `approved Shaper intent changed after definition approval`. The file was restored byte-for-byte; the positive test and post-approval-mutation refusal test then passed.

## Live Magentic acceptance job

- Work ID: `shaper-delivery-v7-live-proof`
- Attempt: `6ba14eb0b8dd4002a0392cb8f8ffc2c8`
- Source commit: `aecabc44a724b48924bd8fbce9c4f4eeae370b80`
- Isolated worktree: `/private/tmp/flow-v7-live-proof`
- Receipt: `.flow/runs/shaper-delivery-v7-live-proof/execution/6ba14eb0b8dd4002a0392cb8f8ffc2c8/receipt.json`
- Result: completed; no pending approval or unknown action.
- Magentic selected `claude-producer` from the approved Claude/Codex candidates and recorded the reason plus the Codex rejection reason.
- Flow observed one changed file, `docs/maf-adoption-design.md`, and a bounded diff with SHA-256 `0db019babc70a7ffd24d727131c71ed38e0480c1c583b278284d706847226542`.
- Flow ran `tests/test_documentation_contracts.py`; it passed.
- The distinct `ollama-verifier` made three completed physical `llama3.1:8b` calls. Its responses were not strong enough for the manager, which then proposed Codex twice; Flow denied both proposals with `producer_already_completed`.
- The receipt links Shaper Contract `b44fe2df5b98132214f9689fb5afbb973642e34190fcdf68423b78a671eaa5dd`, Delivery Charter `1c7695f5d2c044d72b60a5e11fec13c352fd1ebc79c872ea8606e632ba8259a1`, handoff `6d249cfb7f431e70818bbc497958a06ad56ea200edecc9298cb9a37ee71887af`, and lead claim `0743ba21e2d3c849fbb3ff8151d8fbb60f5c8afc234d50c9569e374cbc3b8a36`.
- Full suite in the changed live worktree: 1,316 tests passed, 1 skipped, in 133.094 seconds.

## Evidence verdicts

- Contract and policy implementation: PASS against the implementation branch.
- Live Flow-to-Magentic-to-Claude-to-Ollama route: PASS for dispatch, bounded edit, deterministic test, physical verifier calls, denial enforcement, and receipt linkage.
- Ollama verification quality: LIMITED. Ollama was functional, but the manager considered its responses unreliable and repetitive. The live proof establishes the controlled runtime path, not strong local-model judgment quality.
- Live documentation diff: evidence-only. It contains the proof commit hash and remains in the isolated worktree; it is not part of the implementation branch.

## Remaining follow-ups

- Improve verifier prompts or structured verifier output so Magentic does not spend repeated local calls seeking raw tool evidence the Ollama adapter cannot provide.
- Consider a verifier-call cap distinct from the global delegation cap.
- Add durable SQLite schema migration history before v7 data is treated as a long-lived migration surface.
- Replace mtime-based default attempt selection and represent approved file deletions if later slices need them.
