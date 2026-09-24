# Acceptance criteria

- Deterministic local test observes two completed specialist dispatches with different IDs.
- Checkpoint replay retains one ID and records no additional dispatch.
- Raw participant injection is rejected before MAF build.
- MAF calls manager.replan three times; Flow ledger permits two and denies third.
- Paid providers are never dispatched; validation and limits are documented.
