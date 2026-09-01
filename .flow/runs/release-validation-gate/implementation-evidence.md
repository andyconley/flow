# Implementation Evidence

## Implemented change

- `release.config.cjs` now requires explicit `preview` or `publish` mode. Both
  modes share the exact analyzer and release-note policy; preview omits all
  mutating plugins.
- `scripts/release_gate.py` owns strict plan, evidence, publication, drift,
  remote-baseline, and generated-release-commit contracts.
- `scripts/release_candidate.py` builds local-only candidate and previous-tag
  remotes and runs the thirteen stable deterministic checks through the real
  Flow install/update/runtime surfaces.
- `scripts/release_verify_published.py` verifies public tag, release commit,
  notes, fresh install, upgrade, setup, sync, doctor, runtime smoke, and a
  representative CLI path without mutating published state.
- `scripts/release_reconcile.py` records branch, tag, and GitHub release state
  after a failed publisher without retrying or mutating the remote.
- `.github/workflows/release.yml` is now the four-job
  `analyze -> validate-candidate -> publish -> verify-published` graph with
  workflow-default read permission and publication-only write permission.
- Every external Action is pinned to a reviewed full commit SHA. Candidate log
  files must resolve inside the evidence root and match their SHA-256 records.
- ADR 0002, architecture, CLI, README, and the release failure runbook describe
  the evidence chain, manual limitations, partial-state diagnosis, and
  repair-forward recovery.

## Commit slices

- `e61c74d chore(flow): record release validation gate run`
- `f8fd9d5 feat(release): add validated release planning contracts`
- `83918bc feat(release): validate candidate and published artifacts`
- `0393e46 ci(release): gate publication on candidate evidence`
- `cf00921 docs(release): document release gate operations`
- `02a8254 fix(release): stabilize preview note links`
- `96eeb76 fix(release): seed candidate overlay for doctor`
- `7776703 fix(release): classify isolated doctor warnings`
- `298cca2 fix(release): close validation review gaps`
- `ebdaf02 fix(release): contain uploaded validation logs`

## Superseded transition preview

- Semantic-release 25.0.9 ran through its JavaScript API against `main` in a
  temporary local bare remote with `GITHUB_TOKEN` and `GH_TOKEN` absent.
- Git URL rewriting was scoped to the temporary preview clone. Semantic-release
  received the canonical `https://github.com/andyconley/flow.git` URL for stable
  note links while its push-permission probe resolved only to the local mirror.
- Predicted source: `777670320a65ec713947bea7ca043d3321b5cee0`.
- Previous release: `v0.21.0` at `f15859523ed1508aa83b5f3516ef0786c20c7ca9`.
- Predicted release: minor `0.22.0`, tag `v0.22.0`, nine rendered entries.
- Plan digest: `2529a47953e48c9066d2c65e167b9422436d887fed6aad8d2968c8535280d90b`.
- Notes digest: `47feb0dcce2f89c351254639543775c195764e2ad9730324430469cd0852a168`.

This preview and its candidate artifact are historical evidence only. They are
bound to `7776703`; a final preview and candidate gate will replace them after
the review artifacts and hygiene fixes are committed.

## Superseded candidate proof

The validated evidence artifact
`.flow/runs/release-validation-gate/release/candidate-evidence.json` has digest
`bb5d288db4acf60aad400a6b64d7619789d9f61fa823da04f8e5f93f4f5e3fd8`.
Every stable check passed:

- full Python suite: 755 tests at the superseded SHA
- generated-help consistency
- release staging and transitive imports
- clean tracked tree
- local-only `v0.22.0` fresh bootstrap install
- upgrade from local `v0.21.0` to local `v0.22.0`
- machine and user setup
- Claude and Codex sync checks
- `doctor --check --json`: `ok: true`, zero errors, only the four explicitly
  accepted isolated-run live-client/telemetry warning IDs
- static runtime smoke
- representative structured update check

Per-check duration and log SHA-256 values are stored in the evidence; retained
logs live under `.flow/runs/release-validation-gate/release/logs/`.

## Validation state

- Focused release/security/recovery suite: 50 passed.
- Full repository suite: 767 passed at `ebdaf02`.
- All thirteen injected candidate failures stop later checks; failed evidence
  leaves the fake publication boundary and modeled external state unchanged.
- All eight required workflow mutations are detected. A real source mutation
  removing the publish dependency made the named contract test fail and was
  restored before the passing run.
- Remote-baseline integration rejects moved `main`, moved prior release tag,
  and an existing candidate tag.
- Independent test, security, and operational reviews pass pre-publication.
- Independent quality review found only final-SHA candidate/hygiene evidence
  outstanding; those are being completed before push.
- Remote publication and public-artifact verification: pending; no external
  write has occurred.

## Surrogate boundaries

- Local candidate Git and install/update checks transfer because the Git object,
  tag-selection, copied release tree, and CLI paths are the production code at
  the exact planned SHA.
- GitHub permissions, Action artifact transport, hosted release creation, and
  public network consumption remain unverified until the workflow runs on the
  shared repository.
- Live Claude/Codex discovery, applied model/effort routing, external identity,
  and actual capability grants are manual and outside this slice.
