# Approved v2-only release plan and validation

Tracking issue: [#133](https://github.com/andyconley/flow/issues/133).
The user authorized implementation, normal regressions, push, merge and release.
Live Claude/Codex repair qualification and MacBook changes/sign-in are excluded.
Expertise-retrieval redesign is outside this release.

## Acceptance and implementation handoff

- Make `flow` v2-only. Managed releases retain immutable code/Python/npm
  dependencies under ~/.flow/v2/releases, selected through current. Shared state
  is canonical and survives release switches. No normal source-build or legacy
  fallback is supported. Old user data and native surfaces are protected by
  ownership checks, snapshots, process quiescence and rollback edit checks.
- Replace a legacy/source-bound install once through the new release bootstrap.
  Old source/configuration/history remain preserved; imported work cannot replay
  old approval. New updates fetch published assets and verify their sizes/hashes.
  Opaque native client stores move into stable state with aliases at their old
  paths; migration does not inspect or copy credentials.
- Route definition, solution and plan execution through a persisted LangGraph
  stage node and the Goose coordinator. Exact assignment/actor approval is
  mandatory before dispatch. Stage findings/proposed briefs do not authorize
  implementation. Research edits and uncertain effects are blocked/preserved.
- Build patched Goose automatically from locked upstream source, deterministic
  full-index patch, Rust 1.99.0 and Cargo.lock. Distribute source/patch provenance,
  binary metadata/checksums, verified code and hashed Python wheels. npm uses
  package-lock integrity. Support only Apple Silicon macOS 15+ with Python 3.12
  and Node.js 24; no unqualified target or live-provider claim is made.

## Validation and release gates

Offline/unit/integration checks cover corrupted assets, archive traversal,
failed dependency preparation, source-checkout deletion, managed update/rollback,
user edits, user-overlay/config/history retention, stage authorization/dispatch,
permission pauses, effect reconciliation and unchanged native completion guards.
Candidate/public consumer tests install the actual release-built assets in
throwaway homes and run offline tests, doctor, static recipe/adapter checks and
normal update/rollback. CI never starts provider inference or account login.

The existing release plan, notes digest, exact source identity, candidate-log
hashes, repeated credential-free analysis, refreshed remote baseline and single
publisher remain fail-closed. Build-manifest identity is additionally passed
from the build job to candidate/publication checks. Published tag/changelog,
release notes and public distribution consumers are verified after publication.
Retired-engine installer/sync tests are replaced by the current v2 checks; no
branch protection or security setting is changed.

## Version and recovery

The breaking cutover uses the existing pre-1.0 release policy: expected v0.51.0.
A failed installation leaves the prior selection intact. Rollback refuses user
surface edits instead of overwriting them. A publication failure is reconciled
before any retry; a published failure is repaired forward. Active Studio
installation and MacBook state are not changed by this release work.
