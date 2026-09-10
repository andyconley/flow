# Implementation test state: three-role expertise expansion

- Owner role: test-engineer
- Date: 2026-09-10
- Scope: current-state inspection only; no production, test, evidence, or
  lifecycle artifact was changed.

## Current state

`/opt/homebrew/bin/python3.12 -m unittest tests.test_expertise_composition`
currently passes: 45 tests in 0.032 seconds. That is baseline evidence only.
Its shipped-corpus tests still declare an eight-role composed tuple and require
the repair-2 PM/QR executable boundaries and corpora. The working tree also
still has the five-role candidate surfaces and eight-role current-document
claims. Passing it cannot establish the approved six-role release.

The only repair-3 evidence inputs now present are the frozen
`start-receipt.json`, `preservation-inventory.json`, and
`release-evidence-map.json`. There is no preimplementation verification, final
receipt, mutation receipt, isolated adapter output, validation result, or native
client record yet.

Current PM/QR hashes differ from their pre-repair controls:

| Role | Frozen control SHA-256 | Current SHA-256 | Required final state |
| --- | --- | --- | --- |
| product-manager | `db45fab8…a3592` | `433e3e09…df6c0` | exact control bytes |
| quality-reviewer | `4cd2d84d…a3592` | `b4a3bfd1…d557` | exact control bytes |

Lead-developer currently matches its start receipt hash
`2dc53fe1…c513`; architect and test-engineer still need the same explicit
final hash comparison.

## Acceptance-criterion oracle map

| Criterion | Concrete oracle | Current coverage / missing guard |
| --- | --- | --- |
| 1 — exact cohort | Parse `flow.toml` and assert set equality with `{architect, business-analyst, lead-developer, sre, support-lead, test-engineer}`. | Existing test asserts eight roles including PM/QR. Replace rather than append the cohort expectation. |
| 2 — retained sources, joins, rendering | Hash the six retained role/corpus files against the start receipt; run schema/source/audience/id and forward/reverse-join tests; render each retained role. | Generic schema/join/render tests exist, but no receipt-hash or exact-three-role guard. |
| 3 — named passing evidence | Validate `release-evidence-map.json`: exactly three allowed roles, pass gate, start hashes, locator/entry id, result hash, and four extant record hashes each. | Map exists and is parseable; no automated validator yet. |
| 4 — PM/QR base-only state | Compare body bytes with `git show 2712f5f:<body>`; assert no composed declaration, corpus selected by loader, active vocabulary edge, or rendered Expertise section; assert base agent remains addressable. | Existing tests require the opposite repair-2 PM/QR state. No inactive-surface guard exists. |
| 5–6 — history preservation | Validate the three frozen input hashes first; rehash all 112 inventory paths and both receipt tree digests; write a separate final receipt with zero unexplained deltas. | Frozen baselines exist; no verifier or final receipt exists. |
| 7 — deterministic/mutation proof | Focused tests cover exact cohort, PM/QR inactivity, retained mapping/joins/rendering, and active-doc claims. Run three restored mutations: PM reintroduction, test-engineer removal/map failure, and lead-developer semantic negation while retaining searched words. | No new guards or mutation receipts exist. The prior product deletion mutation is repair-2-only and does not satisfy this criterion. |
| 8 — automated, adapter, doctor, live delivery | Focused/full/help/diff/sync/check/smoke logs; isolated Claude and Codex generated bodies; local two-part doctor comparison; hosted `validate-candidate`; two dated native test-engineer observations. | Only the focused baseline was run. No adapter, doctor, hosted, or live evidence exists. |
| 9 — current claims | Fixed active-document search includes current architecture/file-layout, new summary, validation, and handoff; require three added/six total and reject active five-role-success/eight-role-composed claims while excluding protected history. | Current docs explicitly say eight roles. New current summary and search report do not exist. |
| 10 — bounded change | Capture allowlist and final changed-path classification; every production path must fit the approved surface or have a blocking disposition. | Current diff contains the expected candidate surfaces plus pre-existing `.flow/memory/STATE.md`; no repair-3 classification exists. |

## Smallest non-vacuous proof set

1. Implement a focused composition contract in
   `tests/test_expertise_composition.py` for criteria 1–4 and 7, including the
   three distinct negative mutations. The semantic mutation must negate the
   retained lead-developer obligation (for example, insert `Do not` before
   `first classify reversibility`) while preserving the former searched words;
   a raw substring assertion is insufficient.
2. Add a run-local validator that reads, never rewrites, the three frozen
   inputs; produces `preimplementation-verification.json` before edits and
   `final-receipt.json` after edits; compares every inventory file and both
   documented tree-digest algorithms. This proves criteria 3, 5, and 6.
3. Generate Claude and Codex adapters in isolated outputs and inspect the
   emitted files separately: test-engineer has exactly one Expertise section
   containing **Define a test oracle with a concrete example**; PM/QR have zero.
   Shared `sync.agent_body()` coverage alone is insufficient.
4. Run the approved automated commands: focused suite; full discovery suite;
   `scripts/regenerate-flow-help.py --check`; `git diff --check`; both sync and
   `--check` commands; `flow runtime smoke --target all --json`; `flow doctor
   --json`; and `flow run verify role-method-differentiation-repair-3`.
5. Treat local doctor as two checks: JSON must exit 0 with `ok: true` and zero
   errors; `flow doctor --check --json` must exit 1 with exactly
   `user.claude.runtime_smoke`, `user.codex.runtime_smoke`,
   `project.adoption.runtime_surfaces`, `telemetry.claude.harvest`, and
   `telemetry.plugin_usage`, with no new/error/higher-severity diagnostic. The
   isolated hosted `validate-candidate` doctor remains a hard gate.
6. In fresh native Claude and Codex sessions at reviewed tree `T`, invoke
   `test-engineer` with: “An import must reject `row 7,
   email=\"not-an-email\"` and expose an error containing `row 7` and `email`.
   Define the minimum test oracle.” Each dated record must show client/agent,
   isolated generated-output hash/method, configured model/effort, fixture, and
   response naming the input, user-visible error, integration test level, and
   failure path. Also run `/flow-status` in Claude and `$flow-status` in Codex.
   `unavailable` or `inconclusive` blocks review.

## Stop conditions

- Any frozen-input/inventory mismatch blocks before production edits; any final
  mismatch blocks formal review.
- A mutation that does not fail its named guard, or cannot restore its exact
  hash, blocks review.
- A local doctor result outside the documented two-part contract, a failed
  hosted candidate doctor gate, or a missing isolated generated output blocks
  the associated delivery claim.
- A missing native-client observable blocks acceptance; static smoke cannot
  replace it.

The next implementation change should replace the eight-role/repair-2 test
assumptions with this exact six-role, evidence-preserving contract before any
validation result is claimed.
