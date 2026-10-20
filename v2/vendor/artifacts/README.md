# Retained offline Goose fixture and production assets

The checked-in gzip/JSON retain the previously verified Studio build for
maintainer offline regressions and provenance history. They are not a normal
installer fallback. Historical verification is in [VERIFICATION.md](VERIFICATION.md).

Production release CI runs scripts/build_v2_release.py: it fetches the locked
upstream Goose commit, checks/applies the full-index Flow patch, validates the
source tree, compiles with Rust 1.99.0 and locked Cargo dependencies, and verifies
architecture, system libraries, deployment metadata, signature and executable
behavior. Only Darwin arm64/macOS 15+ is release-qualified. No live provider
qualification is claimed.

Release assets contain a freshly built gzip and provenance JSON, code tarball,
hashed Python wheel closure, release-manifest.json and SHA256SUMS. Every asset
is size/hash checked by the managed consumer before activation. Consumers do
not compile Rust. A maintainer existing-binary packaging shortcut is explicitly
rejected by publication checks. The normal install/update/rollback instructions
are in [the managed guide](../../FLOW_V2_INSTALL.md).
