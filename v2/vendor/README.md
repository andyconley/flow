# Goose integration dependency

Flow v2 uses official Goose v1.55.0 at the exact upstream commit in `goose.lock.json`, plus `goose-native.patch`. The patch carries the necessary native ACP completion and explicit permission/scope error propagation used by this integration. It is not a separate published Goose fork, and no unrelated upstream branch/history is vendored.

`goose.lock.json` records the official repository, base commit, patch digest and Cargo feature set. `../bootstrap.py prepare --build-goose` checks the digest, applies the patch to a clean detached upstream checkout and builds the CLI with the locked Cargo dependencies. Its source/build output lives under ignored `v2/runtime/goose/`. A retained, checksum-verified Apple Silicon executable is also shipped as a lossless gzip archive; see [artifact provenance and consumption](artifacts/README.md). No native account data is committed.

Goose's Apache-2.0 license is included in GOOSE_LICENSE. The patch changes are part of Flow's integration. The original local integration commit is a reference for provenance, not a remotely fetchable dependency: reproducibility uses the official base plus the shipped patch.
