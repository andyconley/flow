# Two-role repair evidence

This directory preserves the second, approved repair separately from the
earlier failed comparisons. `manifest.json` was frozen before either client
arm ran. Every treatment/control pair uses the same prompt, client, model,
effort, turn limit, budget, and body-injection mechanism.

The comparison is intentionally strict. A role passes only when treatment
satisfies every frozen distinctive primary criterion, control satisfies none
of them, treatment passes its counter-case, parity holds, and all four records
complete without client error. Ties fail. Results never rewrite the earlier
raw records.

`results.json` records the independent criterion-level score and immutable raw
response hashes. Both role gates failed. `mutation-check.md` records the
negative deterministic check separately from the behavioral comparison.
`preserved-lead-developer.json` inventories the passing source and evidence
retained outside this two-role run and states the limit of that proof.
