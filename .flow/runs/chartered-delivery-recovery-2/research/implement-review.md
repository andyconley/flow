# Implementation review: chunk 2

- **Reviewers:**
  - `implement-review-quality` (quality-reviewer)
  - `implement-review-security` (security-reviewer)
- **Scope and mode:** both were read-only and ran concurrently over `87bb715..af223c0`.
- **Verdicts:** both recommend approval. Neither found a blocker or a major issue.
- **Invariants that held**, observed by both:
  - only Flow's stored observation is used as evidence, re-validated inside the transaction;
  - refusals mutate nothing;
  - the lock order holds, and a live run or a stale lead is refused;
  - no generation bump, so the recovery chain stays continuous;
  - no way around the binding check, and no false refusals from it;
  - `_append_resolution_locked` is byte-identical to the old append.

| Finding | Disposition |
|---|---|
| Q5 / S-minor-1: the worktree guard compares path strings, so case folding, firmlinks, and bind mounts could slip past it. | **Fixed** in `c90d58c`. It now compares device and inode across ancestors, and there are case-folded and `..` subtests. |
| S-nit-5 / Q6: `send_lock` accepted a hard link, and a symlink surfaced as a raw `OSError`. | **Fixed.** An `fstat` check requires a regular file with one link, and the CLI reports an `OSError` as a refusal. |
| Q2: revalidation was tested only through the digest, and only at the ledger. | **Fixed.** A route subtest uses an intact digest over an invalid result, which refuses `evidence_invalid`. |
| Q3: AC1 `release`, AC7 `supersede`. | **Fixed.** Tests added. The manager-alone check already compares ledger snapshots, because `_authority` includes them. |
| Q4: the v5–v7 test used an attempt that doesn't exist. | **Fixed.** It now also runs against a real v7 ledger row. |
| S-minor-3: `resolve_unknown` accepts v8, so fail-open peeks could reach it. | **Tried and reverted.** An existing structured-verifier test depends on `resolve_unknown` resolving a v8 verifier. **Engineer decision needed.** The CLI reaches v8 only through the guarded route, and `resolve_attempt` refuses v8. Recorded in ADR 0016. |
| S-minor-2: a symlink inside the worktree that points into `.flow`. | **Recorded** as an assumption in ADR 0016: it relies on the Codex sandbox canonicalizing write paths (unverified). |
| S-minor-4: a released or attention lead with an uncertain observed action is stuck. | **Recorded** as a residual in ADR 0016. It fails closed, and abandonment remains available. |
| Q8: the ADR overstated verifier revalidation. | **Fixed:** it now says shape only for a verifier. |
| Q1: M2 is not demonstrated. | **Deviation.** Three mutation attempts all showed a resend is blocked independently by five guards: answer-mode restore, the ledger's replay of completed rows, eligibility's refusal of an allowed row that has a recorded send, worktree drift, and the verifier limits. The zero-resend assertion is kept and runs first. **Engineer to accept or reject.** See `validation/mutations.log`. |
| Q7: the stale `v8_resolution_requires_chunk_2` code in `resolve_attempt`. | **Declined.** It is a correct backstop, and renaming it would churn a merged contract and its test. |
| Q9: two "owner generation" lines in the text output. | **Declined.** The `--expected-generation` label is explicit, and a wrong value fails safe. |
| S-nit-6: reason-code imprecision (lock label, a stale lead inside the guard). | **Recorded.** Both still refuse. The lock label is carried over from 1a. |
