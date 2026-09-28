# Acceptance Criteria

1. `approve-definition` invokes the existing canonical Shaper-intent validator before any lifecycle persistence.
2. Invalid Shaper intent returns a clear failure and leaves `run.json` and `events.jsonl` byte-for-byte unchanged.
3. Valid Shaper intent still approves Definition and seals the expected artifact digests.
4. Focused regression tests reproduce the predecessor failure and prove atomic rejection plus compatibility.
5. Directly affected CLI guidance or documentation accurately states the validation timing.
