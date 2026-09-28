# Plan Review: v8-live-validation-3 (architect, opus)

- **Verdict:** workable on the installed v0.38.0, with no Critical findings. Every subcommand and flag in the plan exists. A successor on the same work id is prepared automatically, and the verifier precondition can be checked from `inspect-delivery --json`.
- **Advisory expertise:** `no_match` (request `45ac5e62-7be9-4232-b2d5-3da4610b87da`).

| # | Severity | Finding | Disposition |
|---|---|---|---|
| I1 | Important | The script paths pointed at the repo `scripts/`, and no interpreter was given. | **Accepted.** Both now use the run-local path with `/opt/homebrew/bin/python3.12`. |
| I2 | Important | The source of N and the working directory were ambiguous. | **Accepted.** For decide, cancel and abandon, N is `.attempt.owner_generation`, cross-checked with `stuck --json`. `.delivery_authority.owner_generation` is the lead generation. Every command runs from `~/src/flow`. |
| I3 | Important | The reset before a successor saved only `git diff`, so untracked and staged changes would be lost. | **Accepted.** The status, `diff HEAD --binary`, an untracked tarball and the sha256s are saved first, after confirming the predecessor is terminal and reaped. |
| I4 | Important | "Supersede has no CLI" is wrong: `flow run delivery-lead … supersede` exists. | **Accepted.** It is recorded as a plan-level correction to R6, which is sealed. It uses the lead generation. |
| S1 | Suggestion | Copy the draft receipt and the attempt directory before abandon, and diff run.json's `delivery` block. | **Accepted.** |
| S2 | Suggestion | Set the successor's expectations from the predecessor's `headroom_remaining`. | **Accepted.** |
| S3 | Suggestion | Handle `CANCEL_TIMEOUT`. | **Accepted:** follow `stuck`. |
| S4 | Suggestion | Follow `stuck`'s `next_command` rather than assuming abandon. | **Accepted.** |
| S5 | Suggestion | Name every evidence file, keep `commands.txt`, and don't run captures under `set -e`. | **Accepted.** |
| S6 | Suggestion | Run the baseline with the charter's exact interpreter. | **Accepted.** |
| S7 | Suggestion | Don't leave an attempt started at handback. | **Accepted.** |
| S8 | Suggestion | The D7 string matches the source, and the timings script pairing is still right. | **Noted.** Record the successor's predecessor digests. |
