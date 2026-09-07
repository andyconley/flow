# Reviewed legacy import

Use reviewed import for completed work whose run folder has no `run.json`.
Flow keeps its review evidence separate from canonical lifecycle closure. A
reviewer must connect the selected final outcome to evidence of completion;
a folder, plan, test count or URL alone does not establish closure.

Preview candidates without writing files:

```sh
flow archive import preview --json
flow archive import preview older-work --json
```

The owning overlay must already have a valid identity. New projects use ordinary
project setup; restore a lost identity from retained records or backup. Import
never allocates a new identity to retarget existing evidence. Any present
`run.json`, including malformed or active state, requires canonical repair. If
one appears after import, the candidate is quarantined for explicit reconciliation.

## Record a review

Select retained local passages for both `final_outcome` and `closure_evidence`.
They may be in the same file. Selectors support Markdown headings with occurrence
numbers and JSON pointers, using the same archive pointer contract as canonical
abstracts. Paths are relative to the owning `.flow` directory. Evidence includes
the owning source UUID, candidate work ID and SHA256 of the complete file.

Prepare a request with the identity and current `fingerprint` from preview.
This illustrative local request uses placeholder UUID/digest/fingerprint values;
replace them with the selected fixture or project values before validation:

```json
{
  "schema_version": 1,
  "identity": {
    "source_id": "11111111-1111-4111-8111-111111111111",
    "work_id": "older-work"
  },
  "action_id": "older-work-review-001",
  "action": "approve",
  "reviewer": "reviewer-name",
  "reviewer_is_author": true,
  "reason": "The final outcome and acceptance passage identify this completed work.",
  "expected_base_fingerprint": "<fingerprint from preview>",
  "closed_at": {"state": "unknown"},
  "closure_assertion": "The acceptance passage confirms completion of the selected outcome.",
  "evidence": [
    {
      "kind": "local",
      "role": "final_outcome",
      "source": {
        "source_id": "11111111-1111-4111-8111-111111111111",
        "work_id": "older-work",
        "path": "runs/older-work/HANDOFF.md",
        "selector": "heading:final outcome:1",
        "digest": "<SHA256 of HANDOFF.md>"
      },
      "explanation": "This passage states the final decision for older-work."
    },
    {
      "kind": "local",
      "role": "closure_evidence",
      "source": {
        "source_id": "11111111-1111-4111-8111-111111111111",
        "work_id": "older-work",
        "path": "runs/older-work/HANDOFF.md",
        "selector": "heading:closure:1",
        "digest": "<SHA256 of HANDOFF.md>"
      },
      "explanation": "This passage records acceptance of the same final outcome."
    }
  ],
  "selected_final_outcome_sources": [
    {
      "source_id": "11111111-1111-4111-8111-111111111111",
      "work_id": "older-work",
      "path": "runs/older-work/HANDOFF.md",
      "selector": "heading:final outcome:1",
      "digest": "<SHA256 of HANDOFF.md>"
    }
  ]
}
```

The selected final source must match a `final_outcome` evidence pointer. Optional
`field_selections` select other abstract fields from retained final evidence;
component selections also require the existing component catalog. An agent can
help prepare the record, but the named reviewer owns its interpretation.
Self-review is allowed; `reviewer_is_author` is `true`, `false` or `"unknown"`.
These are declared identities and relationships, not authenticated signatures.

When evidence establishes the historical date, use `closed_at` with
`state: "known"`, a timezone-bearing `value`, and a `source` matching a closure
pointer. Otherwise keep it unknown. Review time never substitutes for closure
time. Date-filtered retrieval reports omission of unknown-date legacy decisions.

Validate, then apply the reviewed request explicitly:

```sh
flow archive import review older-work --record review.json --json
flow archive import review older-work --record review.json --apply --yes --json
```

Validation is read-only. Apply rechecks the source and current fingerprint under
the overlay writer lock. It also rereads the operator record under that lock and
rejects semantic drift in the reread request; changes to JSON formatting alone
do not change its semantic payload. The request record remains excluded from the
candidate fingerprint. Stale consent needs a new preview and reviewed request.
The CLI assigns review IDs, recording timestamps and revision digests. It never
writes a canonical `run.json` or lifecycle event to manufacture closure.

## Retain external evidence offline

Save a relevant excerpt or export inside the owning overlay before preview.
For each external evidence entry use the same `role`, `source` and `explanation`
fields above, with these capture fields:

```json
{
  "kind": "external_capture",
  "url": "https://example.invalid/reviews/older-work",
  "captured_at": "2026-09-07T12:00:00Z",
  "source_identifier": "review-older-work"
}
```

This fragment supplements an evidence entry; it is not a complete request.
The local pointer cites the retained capture, not the URL. Capture time requires
a timezone; source identifier is optional. Flow verifies the local bytes and
selector without network access. It does not verify current remote status or
prove that the source or reviewer assertion is true. Retain only relevant,
authorized content, without credentials.

These inputs are rejected without publication:

- An approving request with no `closure_evidence` entry.
- A `local` evidence entry carrying `url` or `captured_at`; use `external_capture`
  for that retained source, and keep ordinary local entries local.
- A changed selected file whose digest no longer matches the reviewed request.
- An old fingerprint reused for a new action after another review has committed.

The executable fixture builder in `tests/archive_legacy_runtime_eval.py` creates
complete requests with real fixture identities, selectors and digests. It validates
their structure before any live client is invoked. Fixtures stay isolated from
production run folders.

Missing evidence or contradictory completion claims should receive `unresolved`
or `reject` with an explanation. Structural validation cannot decide whether a
plausible handoff actually establishes closure.

## Withdraw, retry and reapprove

Use a new request with action `withdraw`, a new action ID, current preview
fingerprint, identity, reviewer/author relationship and reason. It needs no
positive closure evidence and still works when that evidence is missing or
malformed generated prose is safely separable from valid review controls.
The historical date can remain unknown. Unreadable control/JSON or broken
history requires recovery; the CLI cannot safely claim withdrawal in that state.

The current envelope is the authority. Replaced complete reviews are retained
under `abstract-history/reviews/<digest>.json` and validated as a linked chain.
History is never an automatic fallback to a prior approval.

Retrying an action ID with its original semantic payload returns the original
receipt and latest effective state. An old approval retried after withdrawal
still reports current withdrawal. A changed payload with the same ID is a
conflict. Retry does not regenerate prose or repair indexes/coverage.

Use `reapprove` with a new action ID, current base and currently verified positive
evidence after a previous decision. Missing or changed evidence makes an otherwise
approved review ineligible without writing a new review. Exact restoration can
restore that unchanged approval's evidence validity; it cannot undo a withdrawal,
rejection or unresolved decision.

## Recover content and derived stores

A committed review survives downstream generation, index or coverage failure.
Inspect each outcome independently. Repair generated content with a targeted
rescan:

```sh
flow archive import rescan older-work --json
flow archive import rescan older-work --base-fingerprint CURRENT_FINGERPRINT --apply --yes --json
flow index rebuild --json
```

Rescan preserves review/history/refinement bytes. If generated content changes,
a retained refinement may become visibly stale until explicitly revalidated.
Rescan cannot grant approval, repair corrupt authority or accept changed evidence.
Preview is read-only and adds a `proposed_operations` object to the result. Its
`abstract` action is `regenerate` when approved content is missing or differs,
otherwise `not_needed`; its `coverage` action is targeted `refresh`. Its `index`
action is `refresh` for eligible content when an established index exists, or
`skipped` with a remedy to run `flow index rebuild` when the first index does not
yet exist. Excluded candidates propose only coverage refresh. Apply rechecks the
current fingerprint before attempting those operations. Rescan updates only
the target's coverage row and refreshes an established projection; first index
creation remains explicit. Canonical backfill continues to exclude legacy
candidates.

Retrieval uses the same per-overlay SQLite store, transient merged BM25 corpus,
ancestor search and response byte caps. Current legacy provenance and evidence
travel with hits; full review history does not. Withdrawn records cannot appear
as current or include-superseded hits, even if refresh failed. A canonical decision
referencing an excluded legacy target keeps its independent closure while the
relationship is reported unresolved.

## Read operation outcomes

`review_commit` is `committed`, `not_committed` or `uncertain`; preview and rescan
use null because they do not commit a review action. `action_revision` identifies
the receipt, while `current_revision` and `effective_disposition` describe the
latest state. Evidence condition is separate from disposition.

| Exit | Meaning | Next action |
| --- | --- | --- |
| 0 | Complete preview, action/replay or repair | Inspect individual outcomes; create a first index explicitly if absent. |
| 2 | Invalid request, stale base, conflicting action or missing consent | Correct the request or preview again. |
| 3 | Confirmed publication with incomplete downstream work | Use the named content/index/coverage remedy. |
| 4 | Unavailable authority/storage or uncertain publication | Inspect diagnostic and exact revision readback; preserve the action ID for retry. |

A filesystem error after replacement can leave a visible revision whose durability
is uncertain. Do not roll back to an older approval or invent a new action ID to
hide that uncertainty. Keep the original request for explicit retry; a still
unconfirmed durability result remains uncertain. Missing FTS5 affects retrieval,
not archive closure or ordinary define/solution work, and never selects a fallback
ranker.

For rescan, a write error after content replacement remains `abstract.state:
"uncertain"` even when the follow-up readback is also unavailable; the result
reports the qualified identity and an inspection/retry remedy, while the current
revision is unknown. A successful write followed by unavailable readback retains
`abstract.state: "committed"`; an error during the write remains uncertain even
if replacement bytes are visible. Inspect authority with a fresh preview and use
its current fingerprint for an explicit rescan retry.

Stage 6 build and runtime evidence is summarized in [the validation record](archive-legacy-import-validation.md).
