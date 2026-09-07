# Reviewed legacy import validation

Stage 6 adds reviewed legacy authority independently of the released archive
retrieval stages 1–5. Its three implementation chunks cover evidence contracts,
review publication, and retrieval/recovery integration. No real historical run
was imported as part of validation.

## Build evidence

The final product implementation is `e33a4c4`. The focused legacy suite passes
35 tests, including a real lock-release interleaving that preserves the original
action receipt after a competing withdrawal. The full suite passes 908 tests in 81.335 seconds. Final delivery
checks are recorded in the implementation run's validation ledger.

These concrete builds were probed successfully; version numbers alone do not
establish FTS5 capability:

| Environment | Python | SQLite | FTS5 |
| --- | --- | --- | --- |
| macOS 26.6 arm64, Homebrew | 3.12.13 | 3.51.2 | available |
| Ubuntu 24.04 x64, setup-python | 3.10.21 | 3.45.1 | available |
| Ubuntu 24.04 x64, setup-python | 3.11.16 | 3.45.1 | available |
| Ubuntu 24.04 x64, setup-python | 3.12.14 | 3.45.1 | available |
| Ubuntu 24.04 x64, setup-python | 3.13.15 | 3.45.1 | available |

The Ubuntu archive/capability jobs passed on
[83fe4b7](https://github.com/andyconley/flow/actions/runs/34154298040).
The delivery ledger retains the final candidate job and exact interpreter output.
The [earlier retrieval build record](archive-retrieval-validation.md#automated-evidence)
and [CLI diagnostics](cli-reference.md#flow-archive-search-query) retain the
existing capability and repair guidance.

Missing FTS5 was also injected into real isolated develop installations. Install
and doctor recorded the missing capability and remedy before lane execution;
ordinary SQLite and review publication continued to work. Retrieval returned
unavailable without an alternate scorer. This injection proves degradation
behavior; it does not claim a naturally FTS5-free build was tested.

## Live proof

The fixed evaluation has 28 scheduled cells across Claude and Codex. Four
withdrawal cells each use three fresh lane invocations, giving 36 required
invocations: withdrawn with failed refresh, explicitly reapproved with damaged
content repaired by rescan, and subsequently changed evidence.

Both generated define and solution surfaces are exercised. Reviewers judge
source citations, declared legacy provenance, unknown historical dates,
applicable conflicts, plausible inapplicability, withdrawal, and unavailable
retrieval. Exit status alone does not establish a semantic pass. Fixed fixture
CLI validation/publication runs separately from model interpretation.

The harness records exact prompts, fixture/source/generated hashes, client
versions, tool streams, response text and authority snapshots before and after
execution. Providers use the operator's existing authenticated session; Flow
commands use isolated fixture homes. Credentials are not copied. Failed or
inconclusive attempts remain retained; corrected inputs receive a new version.
Independent review accepted all 28 scheduled cells, including all 12 withdrawal
substeps. Original malformed-capture and pre-prompt parsing attempts received no
credit; their corrected versions passed. The run ledger retains each judgment.

## Failure and compatibility checks

Automated tests cover publication uncertainty, missing history/evidence,
historical replay, canonical collisions, generated-only repair, unchanged
unrelated coverage rows, unknown-date omission, response byte caps, and long
review chains. A 101-revision fixture verifies reachable history while keeping
old revisions out of query results; it is a resource observation, not an SLO.

A mutation check bypassed legacy eligibility in an identical disposable source
copy. The withdrawal regression failed as expected. That demonstrates detection
of this eligibility defect; it does not establish historical closure truth or
prove every possible filesystem failure.

Local and external documentation examples were run through the actual CLI,
including invalid input, read-only validation, approval, withdrawal and old
approval replay. User adapter sync, parity and static smoke passed. Static
checks support the live evidence and cannot replace it.

Reviewer identity and semantic closure assertions remain declared judgments.
The synthetic cases establish bounded behavior for these fixtures; they do not
measure general model reliability.
