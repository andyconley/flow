# Requirements: Shaper Intent Approval Validation

`approve-definition` must validate the referenced `shaper-intent.json` against the canonical Shaper-intent contract before writing approved digests, run state, or event history.

Invalid intent must produce a clear validation error and leave both `run.json` and `events.jsonl` byte-for-byte unchanged. Valid intent and existing compatible lifecycle behavior must continue to work.

Review amendments, Delivery-plan validation, provider adapters, MAF review application, and unrelated lifecycle behavior are excluded.
