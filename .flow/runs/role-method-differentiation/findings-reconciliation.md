# Findings reconciliation

Status: resolved for formal review. Every implementation and review claim has a
recorded disposition; the release-blocking result remains visible.

| Claim or finding | Disposition | Owner | Basis |
| --- | --- | --- | --- |
| Approved two-role replacement | accepted | Andy Conley | Requirements and acceptance criteria approve minimum PM/QR replacements and preservation of lead-developer. |
| Product and quality corpus/body implementation | accepted | implementation lead | Deterministic tests, exact ids, joins, source fields, and final hashes pass. |
| Product behavioral gate | accepted as failed | quality reviewer | Treatment misses `PM-P2`; control satisfies `PM-P1` and `PM-P3`. |
| Quality behavioral gate | accepted as failed | quality reviewer | Treatment misses `QR-P3`; control satisfies `QR-P1` and `QR-P2`. |
| Missing `results.json` | fixed | root | Machine-readable scores now cite all eight immutable raw hashes. |
| Stale validation and HANDOFF | fixed | root | Both artifacts now describe repair-2, 45 focused tests, eight live records, and failed gates. |
| Missing mutation proof | fixed | root | The selected instruction was removed, the named test failed, the exact text was restored, and the focused suite passed. |
| Stale final-tree checks | fixed | root | Full suite, sync checks, smoke, doctor, whitespace, and final source hashes are recorded. |
| Missing repair-start lead hash | accepted limitation | root | `preserved-lead-developer.json` inventories current source and prior evidence; implementation history supplies the non-mutation claim. |
| Product fixture total-value ambiguity | deferred | next definition owner | Keep as a known fixture defect; it does not alter frozen scores. A successor fixture must supply initial value or prohibit total-value claims. |
| Four live-client checks | deferred | delivery owner | Retained in `.flow/memory/STATE.md`; static checks do not claim completion. |
| Formal quality review | accepted | root | Independent quality review finds criteria 2, 4, and 8 failed and criterion 5 only partially evidenced. |
| Formal proof audit | accepted | root | Independent test review reproduces all frozen hashes, the 45-test pass, and both failed role-gate calculations. |
| Merge/release decision | blocked by evidence | human decision owner | PM and QR fail the strict role gates, so the combined five-role release is ineligible. |

The immutable repair evidence is not changed by these dispositions. Any method,
prompt, fixture, or rubric revision starts a new versioned envelope.
