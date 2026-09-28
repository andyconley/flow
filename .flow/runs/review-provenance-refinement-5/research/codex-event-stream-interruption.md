# Codex Event-Stream Interruption

## Attempt

- ID: `1327f40b59014e87b9c90a3fe03e9803`
- Codex Delivery Lead facts, plan, and progress calls completed successfully.
- Flow authorized one Codex lead-developer producer call.
- The producer call was recorded unknown with `Codex event stream exceeds limit`.
- The worker checkout remained clean; no edit was produced or reused.
- Flow prescribed abandonment. The coordinator sealed the attempt abandoned at owner generation 1; receipt SHA-256: `6334dadea2e8b92bbf29e5b259922690ab556bc7891e8c1ff771a0e2fff33d03`.

## Diagnosis

`cli/codex_worker.py` caps the entire Codex JSONL event stream at 262,144 bytes. A consequential single-call implementation task can exceed that bound through intermediate command/tool events even when its final answer limit is valid. The adapter then treats the physical send as uncertain, correctly prohibiting replay.

## Required codification

- Add a regression using a valid completed Codex stream whose intermediate events exceed 256 KiB while bounded final output remains valid.
- Replace the undifferentiated total-stream cap with a safe bounded evidence strategy (for example, a larger explicit ceiling and/or incremental validated retention) without permitting unbounded memory/disk use.
- Preserve fail-closed handling for malformed, incomplete, timed-out, or genuinely uncertain sends.
- Use a sealed hybrid successor—Codex manager, Claude editing producer, local verifier—to implement this adapter repair without depending on the broken Codex editing path.

