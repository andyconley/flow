# Findings reconciliation

Status: resolved. Andy Conley approved the selected release boundary on
2026-09-09 (America/New_York).

| Claim or finding | Status | Disposition | Owner | Basis |
| --- | --- | --- | --- | --- |
| Repair-2 PM and QR gates failed | observed | accepted | definition coordinator | Frozen scores and two independent formal reviews reproduce both failures. |
| Repair-2 must remain immutable | observed | accepted | definition coordinator | Prior stopping rule and formal review require a new versioned envelope for any changed method or rubric. |
| Release architect, lead-developer, and test-engineer only | recommended | accepted | Andy Conley | Approved after product, requirements, architecture, and testability checks supported the bounded evidence-backed subset. |
| Remove active PM/QR methods while keeping base roles | recommended | accepted | Andy Conley | Approved because no marginal behavioral lift is demonstrated; removal is reversible and compatible with ADR 0008. |
| Retain all five under a two-axis provenance/behavior policy | recommended alternative | deferred | future definition owner | Architecturally viable, but user value and prompt/runtime cost are unmeasured and a general policy exceeds this bounded repair. |
| Run the 24-envelope PM/QR candidate screen now | recommended alternative | deferred | future product owner | No named workflow need or deadline justifies the cost; candidate sources remain unverified. |
| Preserve complete historical evidence | observed | accepted | definition coordinator | The pre-mutation inventory binds 112 files across both evidence roots and the complete prior run; independent recheck found no missing or mismatched hashes. |
| Three retained roles have named passing evidence | observed | accepted | definition coordinator | The release map binds each role/corpus, source locator, result, and four raw records; all hashes recompute. |
| Initial preservation, live-check, mutation, and scope criteria were ambiguous | observed | fixed | definition coordinator | Revised requirements and criteria resolved every product, requirements, architecture, and testability finding except the intentional human boundary decision. |
| Archive search found no precedent | observed | rejected | definition coordinator | Retrieval was unavailable due to `no_index`; manually inspected local evidence remains outside active selection `321754eda89abf939c1f47c9078a57c15ad5b926183b02d940c6169e28df9d57`. |

The approval accepts the two human-owned claims and supersedes only the prior
all-five release relationship. The two-axis admission policy and candidate
screen remain explicitly deferred.

## Planning reconciliation

| Planning finding | Disposition | Basis |
| --- | --- | --- |
| Ship one atomic three-role/six-total release | accepted | Product, requirements, architecture, and testability reports agree that separating active state, evidence, or installed delivery would make the claim incomplete. |
| Continue through commit, merge, and release after formal review | accepted | Andy Conley explicitly selected full delivery during plan engagement. Publication remains downstream of formal acceptance. |
| Delete active PM/QR baseline corpora | accepted | Andy Conley selected deletion; user-owned overlay corpora remain outside the change. |
| Put the current summary at `docs/evidence/three-role-expertise-expansion/README.md` | accepted | The engineer selected the path and it is outside both protected historical roots. |
| Use test-engineer for both native role checks | accepted | The engineer selected one representative newly composed role for Claude and Codex; command discovery remains a separate live check. |
| Modify `.flow/memory/STATE.md` in the candidate | rejected | The file has a pre-existing unrelated delta and acceptance criterion 10 does not include it. Preserve it unchanged and unstaged; no release-evidence claim depends on it. |
| Require one SHA for reviewed tree, source, release, tag, and install | rejected | Formal review binds production digest `T`; final source commit `C` must preserve those production bytes while adding only review/run evidence; semantic-release may then create generated changelog commit `R`. Public/install readback binds to `R`. |
| Report 15 terms after removing PM/QR | rejected | The current file has 18 terms and 23 entries. Removing exactly two terms and entries yields 16 terms and 21 entries. |
| Make semantic-negation proof optional | rejected | Acceptance criterion 7 requires a retained positive obligation to fail after negation even when prior searched words remain. |
| Regenerate frozen start artifacts before implementation | rejected | Validate them without mutation and write a separate preimplementation verification record. |
| Require local strict-doctor exit zero on the known-warning host | rejected | Non-strict doctor must pass with zero errors; strict output must match the exact five-warning baseline with no new warning. Hosted candidate validation remains a hard gate. |
| Reopen PM/QR or the two-axis policy while narrowing | deferred | The approved definition requires a new work item, trigger, verified sources, and fixed budget. |
| Approve the implementation plan, validation contract, and handoff | accepted | Andy Conley approved the complete plan on 2026-09-10 and invoked `flow-implement`. |

Planning inputs:

- `research/plan-product.md`
- `research/plan-business-analysis.md`
- `research/plan-architecture.md`
- `research/plan-testability.md`

## Implementation reconciliation

| Implementation finding | Disposition | Basis |
| --- | --- | --- |
| Initial candidate `T` omitted two inherited production paths | fixed and accepted for formal review | The corrected change surface covers 29 production paths across the complete release range, including `cli/expertise.py` and ADR 0008. Final digest `4e0a00b81c22d5a7cc2136018188e117893e9ff592813b3ccdb53be400dd8f33` passes all candidate checks. |
| Mutation summaries and final command claims lacked durable proof | fixed and accepted for formal review | Three mutation receipts now record commands, failing diagnostics, exact mutated/restored hashes, and passing restoration checks. The command receipt binds 18 logs, including the bounded current-claim search. |
| Static-smoke wording implied four literal manual checks | fixed and accepted | The validation result now distinguishes the two directly executed command cells from the two generic support-lead role cells superseded by the approved, stronger Claude/Codex test-engineer matrix. No support-lead live result is claimed. |
| Active release language could retain a five-role-success or eight-role-composed claim | observed absent and accepted | The focused current-document oracle and bounded active-surface search find only three passing additions and six composed roles. Five/eight-role mentions are rejection rules, preimplementation state, deferred alternatives, or historical discussion. |
| Frozen strict-doctor set had five warnings; final state has four | observed and accepted in formal review | Both doctor modes have zero errors. `telemetry.claude.harvest` improved from warning to `ok` after the planned refresh; no warning was added or escalated. Quality, test, and SRE reviewers independently accept the safer operational state. |
| Pre-existing `.flow/memory/STATE.md` working delta could enter the release | rejected and excluded | Its captured SHA-256 remains `237cf7b512e212f586e9a8d283346244e51932f8cac06bea72e3ff8572d7a8ea`; it remains unstaged and outside `T`. |
| Implementation can advance directly to commit, merge, or release | accepted only through the next `T -> C` gate | Three independent formal reviewers found no critical or important issue and accepted exact `T`. Commit, remote reconciliation, merge, release, install refresh, and post-release client proof remain separate downstream gates. |

Implementation evidence:

- `validation-results.md`
- `evidence/final-receipt.json` (250 checks, zero failures)
- `evidence/change-surface.json`
- `evidence/logs/receipt.json`
- `evidence/logs/current-claim-search.log`
- `review/implementation-quality.md`
- `research/release-readiness.md`
- `HANDOFF.md`

## Formal review reconciliation

| Review finding | Disposition | Basis |
| --- | --- | --- |
| Exact candidate `T` satisfies criteria 1–10 | accepted | Quality, test, and SRE reviewers independently returned ready-to-accept verdicts. Root reruns passed 49 focused tests, 250 frozen checks, help regeneration, diff checking, and run verification. |
| Planned five-warning doctor set became four | accepted as an evidence-contract improvement | `telemetry.claude.harvest` remains observable and is now `ok`; both doctor modes have zero errors and no warning was added or escalated. |
| Candidate review proves merge, release, or installed-client health | rejected | Review accepts only `T`. The plan still requires `C == T`, remote reconciliation, four release jobs, `C -> R` proof, public readback, install refresh, and repeated Claude/Codex checks. |
| Unrelated `.flow/memory/STATE.md` delta belongs in `C` | rejected | Its captured working hash remains outside the 29-path candidate and must stay unstaged. |

Formal review evidence:

- `review.md`
- `review/formal-quality.md`
- `review/formal-test.md`
- `review/formal-sre.md`
