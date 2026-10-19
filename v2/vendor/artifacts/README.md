# Retained Goose build for Apple Silicon

`goose-macos-arm64.gz` contains the exact existing Flow v2 acceptance-tested
Goose executable from the Mac Studio. No Rust build, stripping, relinking or
signing was performed for this package. This is a retained debug build, not an
optimized release build. Its gzip header has no original filename or timestamp.

The adjacent JSON records both SHA-256 hashes, sizes, original and current source
locks, upstream and integration commit IDs, architecture, deployment target and
system dylibs. `../goose-native.patch` and `../GOOSE_LICENSE` accompany it.
Provenance is based on retained local sources and matching installed/build
executable hashes; it is not a signed build attestation.

## Consume without Rust

Use a fresh checkout of this branch on an Apple Silicon Mac, with a native arm64
Python 3.12+ process. From the repository root:

```sh
cd v2
python3.12 -m poc.goose_artifact --extract
python3.12 -m poc.goose_artifact
runtime/bundled-goose/goose --version
cd ..
./install-flow-v2.sh prepare
```

Extraction verifies the source lock, shipped patch, archive size/hash, executable
size/hash, platform and macOS version. It writes only the ignored local
`v2/runtime/bundled-goose/goose`; an existing conflicting executable is preserved
and rejected. The normal dependency preparation above installs Python/npm
packages; it does not compile Rust. Installing/selecting Flow remains a separate,
explicit step described in `../../FLOW_V2_INSTALL.md`.

After extraction, native and scoped Goose jobs use the verified bundled build.
Selection order is an explicit `FLOW_V2_GOOSE_BINARY` override, then a verified
extracted bundled executable, then the existing source-build path. Overrides
retain their existing semantics: they are caller-qualified and bypass bundled
verification. A corrupt/incompatible extracted artifact fails instead of silently
falling back. Other platforms can use a qualified override or `prepare
--build-goose` with Rust. No artifact download or release pipeline is added.

The binary is arm64 Mach-O, declares macOS 11.0 minimum (SDK 26.4), links only
Apple system libraries, and has an ad hoc linker signature. It passes
`codesign --verify --strict` and offline CLI/recipe tests on Studio macOS 26.6.
The declared minimum is not a runtime qualification on older macOS or on the
MacBook. It is not Developer ID signed or notarized; normal macOS download policy
may require user approval. No global security setting should be changed.

## Git size and delivery

The raw binary is 252,884,216 bytes (241.17 MiB). The exact gzip archive is
51,507,861 bytes (49.12 MiB), below GitHub's 50 MiB warning and 100 MiB hard file
limit. This one artifact is therefore stored in ordinary Git, without LFS or
chunking. See [GitHub size limits](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github).
Future binary growth or repeated build distribution should use verified GitHub
release assets instead; publishing releases remains separately authorized work.

## Source patch identity and preservation

The original lock's patch hash was
`6d31c884eaecdb310f95fe231eac123203d9dff5063fb313e28ddd2548f3dc4e`.
Its patch abbreviated index IDs to seven characters. Full-index generation now
matches full-index verification; only those index lines changed. The new patch
hash is `a4bbbc65cbd81603b9b143d313fb0025fc585c9ec7829c9f30b92958ac9d09ef`.
The JSON retains both complete locks. No existing `.flow-v2-patch.json` stamp was
rewritten. An old stamped build checkout will still be rejected by the new
bootstrap's strict lock comparison: preserve it and prepare a separate source
checkout if building again. Do not set `core.abbrev` to work around validation.
