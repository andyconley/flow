# Definition evidence
Question: What should the pilot preserve from existing Flow and Martin precedent?
Method: Primary web sources read earlier in this task and installed Flow standards; local CLI inventory collected without mutation of source.
Findings: Architecture viewer and dependency checker are distinct mechanisms. CRAP relies on analyzer-specific complexity and coverage. Mutation checks test fault detection. Flow already owns behavior-based testing and acceptance against intent.
Implication: Require one review packet with source provenance, explicit boundary policy and distinct quality signals; retain Flow acceptance authority. Do not invent a second lifecycle or pick a universal threshold.
Confidence: High for inspected tool capabilities and standards; medium for applicability to Python; low for predicted review-time benefit.
Limits: Prior archive retrieval unavailable (no_project_overlay); no selection_id. This is manually inspected evidence. No comparative pilot has run. Installed source has no Git metadata; attached hashes are an observation inventory, not a selected baseline. Development checkout is dirty and its overlay is staged for removal.
Follow-ups: During solutioning select a source revision, module boundary, analyzers, presentation and test instrumentation. Pilot must use an isolated snapshot.
Sources: See requirements.md source inventory and installed-source-inventory.json.
