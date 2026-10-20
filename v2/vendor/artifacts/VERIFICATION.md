# Studio worker-fix artifact verification — 2026-10-19

Source was built offline in a separate checkout, using a copy of the existing
toolchain and build cache. The original Goose checkout, target directory,
installed executable and old source stamps remain unchanged.

- Upstream: `2bcb8583a18a0623eb78c9ed845d597ed99fae48` (Goose 1.55.0).
- Integration: `7c755c3dedb17a4b0f3c0c75f2684fddb534e890`.
- Full-index patch SHA-256:
  `a1cf00413949b78c022d7de8145d4cf120609cba3ce2825c13d15bea6cff0054`.
- Executable: 252,874,344 bytes, SHA-256
  `3ce9c3aa715e9e67bb85bc7384d9199db639a3e99f2b62ffce2c080f463b6142`.
- Archive: 51,167,028 bytes (48.80 MiB), SHA-256
  `41136b409ef3c6b8e01f54d87d36060d15f7b85b121dd66027209e1e85dee9f7`.

The binary is arm64 Mach-O, declares macOS 11.0 minimum and SDK 26.4, links only
Apple system libraries, and passes codesign --verify --strict. This deployment
target is not a qualification on older systems. The linker signature is ad hoc;
no Developer ID signature or notarization is claimed. The exact build command is
in the artifact JSON; Rust was 1.99.0 (b940084d7 2026-09-28).

A second source checkout at the locked upstream commit applied the shipped patch
with git apply --index and passed bootstrap.verify_goose_source. Deterministic
full-index validation remains strict; unrelated-edit and old-stamp regressions
remain in the v2 suite.

Offline Rust checks passed: 41 summon/delegation tests, 18 native-completion
tests and 117 ACP-provider tests. The completion transport matrix includes six
new cases generated from the actual pinned guarded adapter definitions with
synthetic events: nonzero and zero exits, untyped shell failure, missing exit,
terminal nonzero exit, and an explicit failed final report. This is replay
qualification, not captured historical wire evidence or live inference.

The known previous extracted executable was verified and retained under its
SHA-256-named backup while the new archive was verified and extracted in this
isolated Flow checkout. Repeating provision reuses the verified executable.
Corrupt/unknown executables and backup collisions remain rejected. Neither
active Studio installation nor the MacBook was updated. Successful live delivery
and authentication in the new private Claude configuration remain unqualified.

The original retained-build report is [preserved here](VERIFICATION-v0.50.md).
