# Studio artifact verification — 2026-10-19

The host was `AndysMacStudio.attlocal.net`, arm64, macOS 26.6 (25G5043d).
Both active launchers (`~/.local/bin/flow` and `flow-v2`) were read directly.
They select the clean v0.49.1 source at
`/Users/andyconley/Documents/Codex/2026-10-18/task-3/flow-v2-installed-tested/v2`,
Flow commit `0ace3f43b99a5bd28c7890ce735722d41118b58a`.
Its default Goose selection is `runtime/goose/target/debug/goose`.

That executable and the retained original build at
`/Users/andyconley/Documents/Codex/2026-10-18/task-3/goose-native-acp-patch/target/debug/goose`
have identical size (252,884,216 bytes) and SHA-256:
`7530c1ff8cdf0d8e68a74ed9b72d20aa38bbdeae6a5e041fb4794a91dbfd8beb`.
The archive decompresses to those exact bytes. No rebuild was needed.

The original build source is clean at integration commit
`106df93b9b260399f705165b67cc7f0fe9ee4c7b`. Its full-index binary diff from
upstream `2bcb8583a18a0623eb78c9ed845d597ed99fae48` is byte-identical to
the newly shipped patch. The installed source is detached at that upstream base,
with precisely the integration patch staged and the original lock stamp as its
only untracked source file. The strict source verifier accepts its full-index
diff; its old stamp remains unchanged. The patch comparison with v0.49.1 changes
only the 27 abbreviated index lines to full IDs, with all other bytes equal.

`file` reports arm64 Mach-O. `otool -l` reports macOS minimum 11.0 and SDK 26.4.
`otool -L` reports AppKit, Foundation, CoreGraphics, CoreFoundation, Security,
SystemConfiguration and `/usr/lib` libobjc, libiconv and libSystem. There are no
Homebrew or build-directory dylib dependencies or LC_RPATH entries.
`codesign -dv` reports an ad hoc linker signature and no TeamIdentifier;
`codesign --verify --strict` succeeds on the extracted executable.

The extracted executable reports `1.55.0`, and `run --help` exposes
`--no-profile`, `--output-format` and `--max-tool-repetitions`. Existing offline
role tests execute the extracted binary to validate valid/invalid result schemas
and render quoted multiline recipe parameters. These checks make no provider or
model calls. The retained earlier
`/Users/andyconley/Documents/Codex/2026-10-18/task-3/flow-v2-installed-acceptance-report.md`
records 35 installed acceptance checks and 92 v2 tests with the same qualified
Goose binary. Earlier live qualification was reused, not repeated.

Current validation: all 100 offline v2 tests pass, with zero skips, including
8 new artifact/source regressions. The suite uses copied Python/npm dependencies
in this isolated checkout and temporary installation homes. Child-process
cancellation tests require process inspection permission. Initial attempts lacked
those fresh-checkout dependencies and sandbox permission; the final complete run
has neither limitation. Distribution inventory and `git diff --check` pass.

The original installed Flow checkout remains clean. The active launchers,
executable and stamped source were preserved. No MacBook operation, installer
activation, merge, release, LFS setup, Rust compilation or provider call was
performed. macOS 11.0 is the binary's deployment target, not evidence of testing
on that OS; the MacBook itself has not been qualified here.
