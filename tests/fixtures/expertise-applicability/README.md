# Retained expertise evidence used by tests

These byte-for-byte copies make the immutable-evidence tests work in a clean
checkout and in the release runner. The originals remain in local Flow runs;
tests read these tracked fixtures so they do not depend on a maintainer's
private `.flow/runs` inventory.

- `retained-v1/manifest.json`: SHA-256 `d2f42382c7c52bc51227596ceb37e58dc5a5f45e77b1edb026441270afa978b0`
- `retained-v1/results.json`: SHA-256 `9101f9c2902ffb34b5077f19c126c736e37e6227896e9438a5b3b9e68d2dee57`
- `lifecycle/lifecycle-migration.json`: SHA-256 `50f1adcdb2a96a3ec9d2383274f1bf4534c972daa4816372f620c122a7309dd8`

Do not regenerate or relabel these files when revising retrieval behavior.
