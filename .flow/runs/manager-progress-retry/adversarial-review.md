# Adversarial Review: manager-progress-retry (definition and plan)

- **Reviewer:** architect (`adversarial-architecture`), read-only, 2026-09-26.
- **Coordinator check:** A1 was confirmed against `_magentic.py:1088-1093` and `delivery_lead.py:25`.
- **Verdict before fixes:** not ready, because A1 was blocking. All findings are now accepted and applied to `requirements.md`, `acceptance-criteria.md` and `plan.md`.

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| A1 | blocking | MAF catches its own exhausted-retry `RuntimeError` (`_magentic.py:1088-1093`) and replans, so 3 unparsable replies would lead to an unrequested replan, not a failed attempt | **Fixed.** The proxy counts consecutive unparsable replies and raises `PolicyAbort` (a `BaseException`) on the 3rd. MAF's give-up never runs, and a test asserts that no replan follows |
| A2 | major | An event written "directly after" the observation could be lost in a crash, and the receipt would then fail validation | **Fixed.** The receipt block is computed at seal time from the completed `manager_calls` rows. Events are written in the same transaction and are only diagnostic |
| A3 | major | Flow's "parsed" was looser than MAF's `_coerce_model`, which needs all five ledger items as dicts. A reply MAF rejects would retry without Flow's check and would increment the round | **Fixed.** A shape check is required in both the runner and the gateway, and a failing reply counts as unparsable |
| A4 | minor | Every backslash-u was treated as a valid escape | **Fixed.** It counts as valid only when 4 hex digits follow, and the AC2 cases are added |
| A5 | minor | MAF's fence regex could extract an inner fenced object from the canonical text | **Fixed.** A runtime round-trip check where MAF is importable, and a corpus case |
| A6 | minor | MAF's `literal_eval` fallback is left out | **Fixed.** Left out deliberately, and ADR 0018 says so. Parity is measured on the text Flow hands MAF |
| A7 | minor | The receipt check wasn't pinned down | **Fixed.** The validator recomputes over completed progress calls, only for v8, and rejects an empty block |

**The reviewer's answers to the plan's questions:**
- A retry has the same prompt digest at sequence+1, which is a new call id, and the ledger accepts it (`execution_ledger.py:1248`, `:1264`).
- Flow never recomputes rounds.
- Resume starts only from a pending-action checkpoint.
- The canonical text never enters `chat_history`.
- Receipts carry `result.output`.
