# Architecture role review

Evidence inventory: `docs/adr/0001-separate-orchestration-contracts.md`, `scaffolds/default/standards/orchestration.md`, `cli/orchestration.py`, `cli/runstate.py`. These were manually inspected outside the archive search, which returned no matches.

Observed: The manifest declares assignments, scopes, capabilities, provider identity, and handback evidence paths. The validator checks declarations and existence, not actual execution, isolation, commit identity, hidden grants, or semantic truth. ADR 0001 reserves `run.json` for lifecycle projection.

Recommendation: Bind one actual attempt, worktree baseline/result, provider, approved inputs, and validation evidence to the existing assignment and handback gate. Keep detailed attempt data in a linked contract. Capture outcome, constraints, delegated authority, and escalation before dispatch.

Challenges and dispositions: Worktree isolation and commit-bound success are included in the draft first slice; failed/no-commit attempts retain diagnostic receipts but cannot pass successful handback. The engineer retains authority over changed judging criteria. Run-local storage is the first-slice assumption; long-term storage and exact receipt representation go to solution.
