# Patched Goose for Apple Silicon

`goose-macos-arm64.gz` contains Goose 1.55.0 with Flow's native-completion patch
and source-bound delegation enforcement. The worker repair required a new
Studio build because the earlier executable could not refuse role-less
Goose delegation. It was built offline in an isolated source checkout using a
copy of the existing Rust toolchain/cache. Original sources, build outputs,
stamps and active installations were preserved. This is a debug build, with a
deterministic gzip header and no post-build stripping, relinking or signing.

The adjacent JSON records hashes, sizes, full source lock, upstream/integration
commits, architecture, deployment target, system dylibs and build command.
`../goose-native.patch` and `../GOOSE_LICENSE` accompany it. Historical metadata
is retained in `goose-macos-arm64-v0.50.json`; the previous binary remains in Git
history and verified extracted copies are retained during upgrade. These are
local provenance records, not signed or reproducible build attestations.

## Consume without Rust

Use a checkout containing this artifact on an Apple Silicon Mac, with a native
arm64 Python 3.12+ process and Node/npm. From the repository root:

```sh
./install-flow-v2.sh prepare
./install-flow-v2.sh install --dry-run
./install-flow-v2.sh install
```

`prepare`, `install` and `update` automatically verify and extract the bundle.
Existing source-bound `flow-v2 install` / `flow-v2 update` also use this behavior
once their source checkout contains this change. Rerunning install/update reuses
the verified executable; it never compiles Rust. A verified known predecessor is
upgraded with its original executable retained under a SHA-256-named backup. Dry runs validate the archive
and report `goose_extraction_planned` when extraction would be needed, without
writing files. A prepared Python environment is still required for install/update.
The release bootstrap `install.sh` continues to select tagged releases; this
branch must be merged and released separately before that path can acquire it.

Extraction verifies the source lock, shipped patch, archive size/hash, executable
size/hash, platform and macOS version. It writes only the ignored local
`v2/runtime/bundled-goose/goose`; an unknown or modified executable is preserved
and rejected. Only the exact predecessor hash listed in metadata qualifies for
a preserved upgrade; extraction verifies the new archive before replacing it. Preparation installs Python/npm packages and does not compile Rust
unless `--build-goose` is explicitly supplied. Installing/selecting Flow remains a
separate step described in `../../FLOW_V2_INSTALL.md`. The standalone
`cd v2 && python3.12 -m poc.goose_artifact --extract` command remains available for
manual extraction and `python3.12 -m poc.goose_artifact` verifies the selected bundle.

After extraction, native and scoped Goose jobs use the verified bundled build.
Selection order is an explicit `FLOW_V2_GOOSE_BINARY` override, then a verified
extracted bundled executable, then the existing source-build path. Overrides
retain their existing semantics: they are caller-qualified and bypass bundled
verification. A corrupt/incompatible extracted artifact fails instead of silently
falling back. Other platforms can use a qualified override or `prepare
--build-goose` with Rust. No artifact download or release pipeline is added.

The binary is arm64 Mach-O, declares macOS 11.0 minimum (SDK 26.4), links only
Apple system libraries, and has an ad hoc linker signature. It passes
`codesign --verify --strict` and offline CLI/recipe tests on Studio macOS 26.6. Native delivery has not been live-qualified for this build.
The declared minimum is not a runtime qualification on older macOS or on the
MacBook. It is not Developer ID signed or notarized; normal macOS download policy
may require user approval. No global security setting should be changed.

## Git size and delivery

The raw binary is 252,874,344 bytes (241.16 MiB). The deterministic gzip is
51,167,028 bytes (48.80 MiB), below GitHub's 50 MiB warning and 100 MiB hard file
limit. This update remains in ordinary Git, without LFS or chunking. See
[GitHub size limits](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github).
Future binary growth or repeated build distribution should use verified GitHub
release assets instead; publishing releases remains separately authorized work.

## Source patch identity and preservation

The current full-index patch SHA-256 is
`a1cf00413949b78c022d7de8145d4cf120609cba3ce2825c13d15bea6cff0054`.
It applies to upstream `2bcb8583a18a0623eb78c9ed845d597ed99fae48` and produces
the source tree recorded at `7c755c3dedb17a4b0f3c0c75f2684fddb534e890`.
The earlier artifact and original seven-character-index lock remain documented
in the historical JSON and [verification report](VERIFICATION-v0.50.md).
No existing `.flow-v2-patch.json` stamp was rewritten. An old stamped source
checkout remains rejected by strict lock comparison: preserve it and prepare a
separate source checkout if building again. Do not set core.abbrev as a workaround.
