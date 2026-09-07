# Archive retrieval validation

The implementation covers abstracts, canonical backfill, cached coverage,
ancestor-aware retrieval and define/solution behavior. Reviewed legacy import
remains a separate delivery. This record supports implementation review; it is
not release approval or a guarantee about arbitrary model responses.

Acceptance review of `7c8f340` found four defects beyond that initial evidence:
malformed identity could block closure, active lane work invalidated archive
indexes, malformed prose discarded valid controls, and SQLite storage failures
received an FTS5 remedy. The correction tests in
`tests/test_archive_acceptance_repairs.py` exercise those cases, including real
lifecycle transitions and historical supersession links. They fail against the
original implementation and pass with the corrections. Storage failures are
injected at the query boundary; actual disk exhaustion is not claimed.

The corrected local suite passed **873 tests**. Seven new regression tests cover
the four findings, including Python 3.10 message-based storage diagnostics and
extended SQLite error codes. No generated lane instructions changed in this
correction, so the earlier provider traces retain their stated scope and limits.

## Automated evidence

The local full suite passed 866 tests on macOS arm64, Homebrew CPython 3.12.13
and SQLite 3.51.2. Subsequent resource tests passed after tightening the handling
of extremely large top-k values. The mutation check removed closure-authority
quarantine: its regression failed, then passed after restoration.

The [Ubuntu matrix at implementation commit dd9e040](https://github.com/andyconley/flow/actions/runs/34119318436)
passed 70 archive and five capability tests in every row. The
[follow-up matrix at 2268e4a](https://github.com/andyconley/flow/actions/runs/34136980120)
also passed. Runner image: Ubuntu 24.04 x64 `20260831.293.1`.

| CPython build supplied by setup-python | SQLite | FTS5 | Additional FTS5 install |
| --- | --- | --- | --- |
| 3.10.21 | 3.45.1 | Available | None |
| 3.11.16 | 3.45.1 | Available | None |
| 3.12.14 | 3.45.1 | Available | None |
| 3.13.15 | 3.45.1 | Available | None |

These results apply to the executed builds. They do not imply that every build
with the same Python version includes FTS5. Install/update and doctor probe the
selected interpreter. Tests also inject missing FTS5 into the actual isolated
installer: installation succeeds, retrieval is unavailable, ordinary SQLite
works, and diagnostics identify the interpreter and install/select remedy.

## Lane evidence

Actual Claude and Codex runs exercised both define and solution:

- A proposal conflicting with applicable current guidance is visibly adapted
  or dispositioned before advancing.
- Known-component ancestor benchmark, legacy-v1 and child-override precedents
  are rejected when their stated conditions exclude the proposal. The child
  fixture includes anchored whole-run supersession and identical parent/child
  work IDs. Twelve final cells passed independent review.
- Missing applicability conditions cause source inspection and an unresolved
  question with an owner, rather than invented conditions.
- An unchanged second turn does not search again. Explicit narrowing replaces
  the active selection while retaining material decisions and earlier transcript.
- Pre-recorded unavailable FTS5 produces a nonzero retrieval result while both
  lanes continue, without another scorer or capability repair.
- Vocabulary drift produces a lexical miss. The lane instruction explicitly
  separates subsequent manual evidence from the active retrieved selection.

Early harness permission failures and an ambiguous manual-source attribution
were retained as failed evidence, not counted as clean passes. Later runs
explicitly separated manual evidence, though some Claude prose still used loose
“hit” terminology or embellished hidden ancestor scope. Those non-dispositive
language limitations remain recorded; this is not general model-reliability proof.

The frozen ranking corpus contains 52 documents and 27 queries, 21 involving
ancestors or cross-overlay behavior. Five zero-overlap targets remain owned
source/query/tokenizer limitations. No precision target or semantic recovery
claim was added.

## Resource and installation observations

A local 1,000-record unfiltered experiment measured about 3.20 seconds for one
source assessment and 6.67 seconds for streamed ranking with verified five-record
prefix. Whole-process peak RSS, including fixture creation and rebuild, was about
104 MB. These are observations, not an SLO or universal memory ceiling. Graph
size and the largest individual source/envelope still affect memory use.

Queries require writable temporary storage but do not repair project or ancestor
archives. A huge top-k with a tiny byte budget loads only the first nonfitting
payload. Counts still cover all eligible matches.

Installed Claude/Codex adapter sync checks and static runtime smoke passed;
doctor confirmed FTS5 availability. Existing telemetry, adoption and manual
runtime-proof warnings remain separate. No real archive backfill was performed,
and no resident-context or token-cost savings are claimed.

Reproduce focused checks with `python -m unittest discover -s tests -p 'test_archive*.py'`
and `python -m unittest tests/test_retrieval_capability.py`. The standalone
`tests/archive_runtime_eval.py` prepares fresh isolated lane fixtures;
`tests/archive_scale_eval.py --records 1000` records scale observations.
