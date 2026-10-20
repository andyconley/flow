# Independent final review

A separate read-only reviewer examined the full integration diff against released main `28d828a`, source, distribution wiring and retained test evidence. No active installation, credential store or live model was accessed by the reviewer.

The review found three defects, fixed before submission:

- Recover effective ready status from the audited CURRENT receipt after a crash between pointer publication and ready-status writing. Readonly MCP sees the recovered status too.
- Preserve local edits/deletions without conflicts when upstream still matches the merge base. Genuine divergent updates remain conflicts.
- Bypass the namespace bridge for cached operations and preserve distinct per-attempt wire audits, referenced from each execution record.

The review also found the offline workflow omitted corpus-only changes. Both push and PR path filters now include `knowledge/**`, with a regression check.

The reviewer rechecked all four fixes and reported no remaining substantiated publication blocker, conditional on full regressions. The full suite then passed **201 tests** with local Git/setup/HTTP fixtures enabled (`evidence/review-fixed-regressions.log`). A prior invocation from repository root failed test imports because it omitted the required v2 module path; its log is retained separately (`evidence/independent-review-regressions.log`). The corrected invocation ran from v2. Distribution lock/inventory and whitespace checks also pass.

## Exact install and update behavior

The supported consumer is a verified managed Darwin-arm64 release, not this source checkout. Tracked knowledge cards/manifest are included by release git archive. Install/update seeds or reconciles notes under `~/.flow/v2/state/knowledge`, outside replaceable runtimes. Shared corpus fetch can update that component independently without upgrading Flow; local edits/deletions and conflicts are retained. Backups and authored export do not depend on the runtime.

Installation does **not** provision Basic Memory/CocoIndex, model weights or embedding cache. These require explicit local wheelhouse setup and configure/build commands in README.md. Seeded-but-unprovisioned stores block agent submission explicitly; there is no substitute search. No knowledge runtime is downloaded on agent launch. Fresh-install tests exercise installer control flow and a real interpreter with pip/npm stubbed; separate actual pip empty-wheelhouse failure and real model/BM execution evidence are retained. A freshly built consumer release with all downloaded assets has not been installed as part of this review.

Managed write/edit/delete/fetch/restore enqueue work. Ordinary workflow startup and standalone non-native query/graph reads catch external edits; active jobs poll every five seconds. Readonly native MCP does not start enrichment. Outside a running Flow session, external edits require either the optional foreground `flow knowledge watch` loop or catch up on the next ordinary workflow/read. No launchd/background service is installed. Version, doctor and status are inspections, not trigger promises. Failed fingerprints remain visible and require a changed input/version or explicit retry; no repeated automatic failure loop.

## Qualification and remaining limits

The recorded actual readonly production ACP task passed on the explicitly selected local Codex ACP/Ollama `gpt-oss:20b` configuration with namespace compatibility enabled. It is not a Qwen success, a general provider qualification or a complete code-changing multi-role workflow. Qwen failures remain preserved. Final lifecycle corrections were regression-tested; the live model task was not repeated unnecessarily after these changes.

The corpus contains all 21 existing authoritative cards for six of 13 roles. Seven roles have no authoritative cards; no expertise was fabricated. Semantic ranking is imperfect and inferred edges remain suggestions. Notes and backups/generations have no automatic retention cleanup.

This review authorizes no merge/release. Parent review of scope/results remains required. The isolated task model server is stopped; active installs and original sources remain untouched.

## Provisioning usability follow-up

`flow knowledge doctor` is a supported no-install diagnostic command. It reports Python, audited BM/CocoIndex, offline embedding cache and local model separately; accepts proposed `--python`, `--cache`, `--model`, `--ollama` before configure; and prints exact setup/wheelhouse/configure commands including the installed lock path. Ordinary status includes the diagnostics/setup hint. Missing inputs return nonzero and never switch retrieval or download resources. Real isolated diagnostic evidence passed dependencies/cache and explicitly failed the intentionally stopped local model server (`evidence/doctor-local-model-stopped.json`). All 204 local regressions passed (`evidence/provisioning-reviewed-regressions.log`).

The separate reviewer also checked the diagnostic follow-up. Its two findings (effective settings/custom-home command preservation and eager offline cache validation) were fixed and re-reviewed with no remaining substantiated blocker.

## Hosted consumer follow-up

At `f352316`, the real hosted Darwin-arm64 package build and fresh installation succeeded, followed by failure in four permission/retry test cases. Their mocked providers accidentally inherited the installed consumer's seeded-but-unprovisioned HOME, so the legitimate knowledge preflight blocked their mock dispatch before the intended permission boundary. The failure is retained in `evidence/hosted-consumer-failure-f352316.log`.

Only the two mock test classes now select their own disposable knowledge homes. Every existing assertion and the production readiness implementation is unchanged. A separate reviewer verified no assertion weakening. The full 204-test suite passed under a seeded unprovisioned disposable HOME (`evidence/seeded-consumer-regressions.log`); the distribution test still verifies genuine missing provisioning blocks provider launch. Final hosted acceptance requires the subsequent exact-head run.
