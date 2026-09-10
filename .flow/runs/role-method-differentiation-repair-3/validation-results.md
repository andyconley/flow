# Validation results: three-role expertise expansion

- Work item: `role-method-differentiation-repair-3`
- Candidate: production tree `T`
- `T` SHA-256: `4e0a00b81c22d5a7cc2136018188e117893e9ff592813b3ccdb53be400dd8f33`
- Source revision under the working tree: `2712f5f1fb7f3ecabbc0bbcb77cdf9cd33431208`
- Branch: `codex/role-method-differentiation-repair-3`
- Overall implementation verdict: ready for independent acceptance review

## Result

The active baseline now composes exactly six agents: architect,
business-analyst, lead-developer, SRE, support-lead, and test-engineer. The
architect, lead-developer, and test-engineer sources and corpora retain their
frozen hashes. Product-manager and quality-reviewer match the frozen base-role
bodies and have no baseline corpus, composed declaration, vocabulary edge, or
generated Expertise section.

The previous two PM/QR evidence generations remain present and byte-identical.
They still record the failed treatment/control outcome. The current release
summary maps only the three roles with passing gates.

## Acceptance mapping

| Criterion | Evidence | Verdict |
| --- | --- | --- |
| 1. Exact six-role cohort | Parsed-set test plus final receipt `active.composed_roles` | observed pass |
| 2. Retained role boundaries, corpora, sources, joins, and rendering | Frozen six file hashes, release map, schema/join/renderer tests | observed pass |
| 3. Exact three-role evidence summary | `release-evidence-map.json`, `docs/evidence/three-role-expertise-expansion/README.md`, final receipt | observed pass |
| 4. PM/QR restored and inactive | Frozen base-body hashes, absent corpora, manifest/loader/renderer tests, isolated and installed readback | observed pass |
| 5. Failed history preserved | 112 per-file checks and both historical tree digests | observed pass |
| 6. Final receipt | `evidence/final-receipt.json`: 250 checks, zero failures | observed pass |
| 7. Deterministic and mutation proof | 49 focused tests plus all three restored mutations | observed pass |
| 8. Repository, generated, runtime, doctor, and native clients | 996-test suite; sync/check/smoke/doctor; Claude and Codex role records | observed pass, with the strict-doctor baseline improvement documented below |
| 9. Current three-role/six-total claim | Fixed-surface search and current-document test | observed pass |
| 10. Bounded change surface | `evidence/change-surface.json`; full `origin/main` predecessor range plus repair-3 tree, no out-of-scope production path | observed pass |

## Deterministic checks

| Check | Observed result | Time (UTC) | Durable log |
| --- | --- | --- | --- |
| Preimplementation frozen verification | 157 checks, 0 failures | before the first production mutation | `evidence/preimplementation-verification.json` |
| `/opt/homebrew/bin/python3.12 -m unittest tests.test_expertise_composition` | 49 tests passed | 2026-09-10 11:57:13 | `evidence/logs/focused.log` |
| `/opt/homebrew/bin/python3.12 -m unittest discover -s tests` | 996 tests passed in 86.050s | 2026-09-10 11:53:45–11:55:11 | `evidence/logs/full-suite.log` |
| `/opt/homebrew/bin/python3.12 scripts/regenerate-flow-help.py --check` | generated help and README up to date | 2026-09-10 11:57:13 | `evidence/logs/help-check.log` |
| `git diff --check` | exit 0 | 2026-09-10 11:57:13 | `evidence/logs/diff-check.log` |
| User Claude and Codex sync plus `--check` | all four exit 0 | 2026-09-10 11:55:44–11:57:13 | `evidence/logs/sync-*-user.log`, `evidence/logs/sync-*-check.log` |
| Isolated Claude and Codex sync plus `--check` | all four exit 0 | 2026-09-10 11:56:22–11:57:13 | `evidence/logs/isolated-sync-*.log` |
| `flow runtime smoke --target all --json` | `ok: true`; 55 Claude and 52 Codex static checks passed | 2026-09-10 11:57:13 | `evidence/logs/runtime-smoke.log` |
| `flow doctor --json` | exit 0, `ok: true`, 0 errors, 4 warnings | 2026-09-10 11:57:13 | `evidence/logs/doctor-normal.log` |
| `flow doctor --check --json` | expected strict exit 1, `ok: true`, 0 errors, same 4 warnings | 2026-09-10 11:57:13 | `evidence/logs/doctor-strict.log` |
| Final frozen, active-state, complete-candidate, log, and live-capture verification | 250 checks, 0 failures | 2026-09-10 12:18 | `evidence/final-receipt.json` |
| Focused current-document oracle plus bounded active-surface search | pass; no affirmative five-role-success or eight-role-composed claim | 2026-09-10 12:17 | `evidence/logs/current-claim-search.log` |
| `flow run verify role-method-differentiation-repair-3` | `ok` | 2026-09-10 11:57:13 | `evidence/logs/run-verify.log` |

The full-suite output contains expected stderr from tests that deliberately
exercise missing repositories, temporary Git remotes, managed paths outside a
root, and usage-store freshness. The test runner completed with `OK` and exit
zero.

Of runtime smoke's four manual prompts, the two command-discovery cells were
executed directly. The two generic cells naming `support-lead` were superseded,
rather than literally executed, by the approved and more change-relevant
Claude/Codex `test-engineer` matrix. Both independent implementation reviewers
accepted that plan-specific substitution; no support-lead result is claimed.

## Mutation proof

Each mutation was made against the real working candidate, its named guard was
observed failing, and the original bytes were restored before the passing
focused run.

| Mutation | Detection | Restoration |
| --- | --- | --- |
| Reintroduced PM composition | inactive/cohort guards failed and named `product-manager` | exact original SHA restored; focused suite passed |
| Removed test-engineer composed declaration | exact cohort guard failed and named `test-engineer` | exact original SHA restored; focused suite passed |
| Negated the lead-developer positive obligation while preserving its former vocabulary | positive semantic-obligation guard failed | exact original SHA restored; focused suite passed |

Detailed commands, original/mutated/restored hashes, exit statuses, diagnostic
excerpts, restoration proof, and raw logs are in `evidence/mutations/` and
`evidence/logs/mutation-*.log`.

## Generated and installed adapters

An isolated home at `/tmp/flow-repair3-isolated.UKqD5T` was synced for Claude
and Codex, then checked with both `--check` commands. Its generated files were
compared with the real user develop install. All six inspected pairs were
byte-identical.

- Claude test-engineer:
  `95f1c349b92baeea9d1247ff897781529c1851bfbc3d0d78d871b74b2b6a518d`
- Codex test-engineer:
  `a0b7e8b13b3c0d8e2b237d23d739308eb691eb9958e9d5b7452e0d69b508cbe5`
- Test-engineer has exactly one generated Expertise section in each client.
- PM and QR have zero generated Expertise sections in each client.
- Claude declares `sonnet` / `medium`; Codex declares
  `gpt-5.6-terra` / `medium`.

The exact PM/QR hashes and command readback are in
`evidence/isolated-adapter-inspection.json`; every final command, time, exit,
and log digest is indexed by `evidence/logs/receipt.json`.

## Native-client checks

Both clients used the same malformed-email fixture. Both results explicitly
name the representative row-7 input, an observable error containing `row 7`
and `email`, integration level, and the failure path.

- Claude: observed from a fresh native `test-engineer` invocation; session
  `626bdb33-cbbf-44c0-942f-58d53009da56`, model
  `claude-sonnet-5`, effort `medium` from the invocation.
- Codex: observed from native parent
  `01a08b07-309e-77d2-a37e-7fb4ae845f07` spawning child
  `01a08b07-46e0-7a23-9f1c-bb30793b4842` as `test-engineer`; the child
  settings event records `gpt-5.6-terra` / `medium`.
- Claude `/flow-status`: observed in fresh session
  `f9dc01ab-c663-492a-9881-94bbdc9a68f0`; the skill loaded and reported
  `implementing` with `mark-handback-ready` next.
- Codex `$flow-status`: observed in fresh thread
  `01a08b0e-27bc-7533-b9a9-9670204c9740`; the skill loaded and reported
  the same state and transition.

The complete responses, transcript hashes, generated-source identities, and
per-check statuses are in `evidence/live-client-records.json`; bounded raw
captures are in `evidence/live/`. The three later production mutations were
deliberate negative tests. Each was restored to its frozen SHA before `T` was
recomputed and its 250 checks ran, so the native checks and `T` bind to the
same production bytes.

## Scope and preservation

`evidence/change-surface.json` defines `T` over 29 active production paths and
explicit PM/QR corpus-absence markers. It includes the inherited
`cli/expertise.py` and ADR 0008 changes from `origin/main..HEAD`, along with
the complete repair-3 working production surface. No file is staged. The
unrelated `.flow/memory/STATE.md` working delta remains byte-identical to the captured start hash
`237cf7b512e212f586e9a8d283346244e51932f8cac06bea72e3ff8572d7a8ea`
and is excluded from `T` and the future feature commit. The predecessor commits
already carry a different `STATE.md` blob; the future feature commit keeps that
HEAD blob by leaving the current working delta unstaged.

The active-claim search found no current five-role-success or
eight-role-composed claim. Its only match is the validation plan's explicit
instruction to reject such a claim.

## Doctor deviation

The approved plan froze five strict-doctor warnings. The final run has four:

- `user.claude.runtime_smoke`
- `user.codex.runtime_smoke`
- `project.adoption.runtime_surfaces`
- `telemetry.plugin_usage`

`telemetry.claude.harvest` changed from warning to `ok` after the planned
harvest/normalize refresh; doctor reports the harvest as fresh at
2026-09-10 11:19:49. No warning or error was added, severity did not increase,
and all release-relevant source, sync, agent-policy, overlay, and FTS5 checks
remain `ok`. This is an observed improvement from the frozen host baseline,
not a product-code fallback or omitted diagnostic. The implementation quality
review and SRE review both accept the safer state operationally; formal review
must record the evidence-contract disposition because the plan used exact-set
wording.

## Review boundary

Formal `flow-review` must assess production digest `T`, this bounded working
diff, all 112 protected paths, the native records, and the doctor deviation.
No source commit, merge, or release has occurred. After acceptance, the final
source commit `C` must reproduce every production hash in `T`; later additions
before `C` are limited to declared review and run evidence.
