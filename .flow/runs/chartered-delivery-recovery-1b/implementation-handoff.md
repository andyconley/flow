# Implementation Handoff: chunk 1b

- **Branch:** `codex/chartered-delivery-recovery-1b` off `main` `7b2b7ff`, worktree `/Users/andyconley/.codex/worktrees/delivery-recovery/flow`.
- **Read first:** `requirements.md` (E1–E5), `plan.md` (anchors and commit sequence), `validation-plan.md`, parent `research/plan-architecture.md` items 8–10, `docs/adr/0016-chartered-v8-recovery.md`.
- **Commits:** the three in `plan.md`, Conventional Commits, full suite green after each.
- **Rules:** v5–v7 behavior unchanged; every refusal mutates nothing; keep `delivery_control`'s lazy ledger import; the first attempt's envelope stays byte-identical.
- **Done when:** AC1–AC6 in `acceptance-criteria.md` pass, the mutation checks are recorded in `validation-results.md`, and `HANDOFF.md` is written.
