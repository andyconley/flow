# Implementation Handback

## What changed

This slice establishes the Flow-owned Shaper-to-Delivery boundary. It adds canonical Shaper Contract, Delivery Charter, ownership handoff, and generation-fenced Delivery Lead claim artifacts; an atomic, idempotent `start-plan` transition; protocol-v7 projection into the existing ledger, gateway, checkpoint, receipt, and supervised Magentic paths; strict producer/verifier roster and specialist-definition binding; v6 read-only inspection; `flow run inspect-delivery`; and the associated CLI, help, ADR, compatibility fixtures, and tests.

Magentic can select an approved Claude or Codex producer and record a bounded rationale. Flow grants and observes the scoped action, verifies the worktree diff and targeted test, then requires a distinct read-only Ollama verifier before sealing a charter-linked receipt. Stale generations, changed approved intent, out-of-charter requests, duplicate producer work, malformed legacy records, and unsafe resume paths fail closed.

## Why

The change turns approved Shaper intent into durable, inspectable delivery authority without making runtime sessions or provider credentials authoritative. It keeps Flow as the policy and evidence boundary while allowing Magentic to coordinate the approved delivery work.

## Validation

- The full implementation suite passed: **1,316 tests passed, 1 skipped** in 131.079 seconds.
- Focused contract, lifecycle, compatibility, gateway, recovery, and Magentic checks passed; the approval-boundary suite passed after binding the reviewed `shaper_intent` bytes and digest.
- Orchestration dispatch validation passed with no findings.
- `git diff --check` passed.
- Mutation evidence is recorded: inverting the approved-intent comparison caused the atomic start-plan test to fail; the source was restored byte-for-byte and the guard passed again.
- Independent quality review: **APPROVE**. Data review: acceptable for v7 handback.

## Live proof

The live proof run `shaper-delivery-v7-live-proof`, attempt `6ba14eb0b8dd4002a0392cb8f8ffc2c8`, completed from source commit `aecabc44a724b48924bd8fbce9c4f4eeae370b80`. Magentic selected the approved Claude producer, Flow observed one scoped edit to `docs/maf-adoption-design.md`, and the targeted documentation test passed. A distinct Ollama verifier made three completed physical `llama3.1:8b` calls. Flow enforced the single-producer rule and denied later Codex proposals as `producer_already_completed`; the receipt is complete with no pending approval or unknown action.

This proves the controlled Flow-to-Magentic-to-Claude-to-Ollama dispatch, diff/test observation, denial enforcement, and receipt linkage. The Ollama calls establish that the provider path is functional, but their semantic verification responses were limited and repetitive; they are not strong evidence of independent local-model judgment quality.

## Limitations and next actions

- The implementation commit `aecabc44a724b48924bd8fbce9c4f4eeae370b80` is local and has **not been pushed or merged**.
- Add durable SQLite migration history before treating v7 schema evolution as a long-lived migration surface.
- Improve verifier prompts or structured verifier output and consider a verifier-specific call cap.
- Later operability work can replace mtime-based default attempt selection and add explicit deletion evidence if needed.
- The live documentation diff is evidence-only in its isolated worktree and is not part of the implementation branch.
