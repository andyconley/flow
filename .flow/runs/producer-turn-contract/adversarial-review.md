# Adversarial Review: producer-turn-contract (definition and plan)

- **Reviewer:** architect (`adversarial-architecture`), read-only, 2026-09-26.
- **Advisory expertise:** `no_match` (request `ca18482d`); no entries delivered.
- **Coordinator check:** F1 confirmed at `cli/delivery_gateway.py:419-427` (the declared-regression baseline records allowed-file hashes), and F6 at `:495` (the 32,000-byte manager message cap).
- **Verdict:** no blocking findings. All majors are accepted and applied to `requirements.md`, `acceptance-criteria.md`, `plan.md` and `validation-plan.md`.

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| F1 | major | With a declared-regression baseline, an editor that does nothing reaches the "no observed change" branch, so D6 isn't fully fixed; the AC3(c) identical-bytes fixture is also unreachable | **Fixed.** (c) now says "editor made no edit: the allowed paths still match the pinned baseline", and its test uses a declared-regression baseline |
| F2 | major | `manager_adapter` is the wrong seam for AC1, and the fixtures only produce protocol 8 | **Fixed.** A pure `_execution_facts` helper is parameterized over protocols 5–8, and a fake supervisor captures the task for AC2b |
| F3 | major | Manager `prompt_digest` covers the task, so an attempt paused before the change can't be resumed after it | **Accepted** under no-backcompat. The requirements assumption is corrected, and AC7 adds a pre-merge scan |
| F4 | minor | The one-call refusal applies across all producers, and "exactly one" means at most one | **Fixed.** The wording is now "one call in total … any second editor call" |
| F5 | minor | The D6 split changes only the message; recovery wraps it as `WORKTREE_DRIFT` detail | No action |
| F6 | minor | The size of the added line, given how often Magentic repeats the task | **Fixed.** The line is about 300 bytes, and a test caps the block at 1,500 bytes |
| F7 | minor | The doc anchor didn't exist | **Fixed.** The paragraph starting "The current chartered path is v8" |
| F8 | minor | AC4 is feasible; pin the failure field | **Fixed.** Added to AC4 and the plan |

The reviewer couldn't read `.flow/runs/v8-live-validation-2/validation-results.md` because it's on the unmerged PR #43 branch. The D6/D7 facts it holds are restated in `requirements.md`.
