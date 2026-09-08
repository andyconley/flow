# ADR 0008: Author expertise entries as JSON-LD, owned per role

- Status: accepted
- Date: 2026-09-07
- Decision owner: repository owner
- Related work: agent expertise corpus, pilot roles business-analyst, sre, support-lead
- Scope: authored storage format, citation shape and ownership boundary; retrieval, sync composition and the two-layer merge mechanism are named here but not approved by this ADR

## Context

The expertise capability shipped its pilot in v0.26.0: seventeen five-part
entries across three roles, a competency vocabulary, and a two-arm validation
record. The bibliography and provenance handoff left the storage format, the
citation shape and the location of source pinpoints open, and directed that
they be settled in solutioning. The namespace was decided as
`https://andyconley.github.io/flow/ns#` bound to prefix `flow`, and the record
model as schema.org `LearningResource`.

An earlier revision of this ADR chose authored Markdown with a central
id-keyed source registry. It was never merged and nothing depended on it. It is
replaced rather than superseded, because two of its arguments do not survive
examination.

**The readability argument was self-undermining.** It defended Markdown on the
grounds that entries are read by a person reviewing a role, while
simultaneously deciding that sync composes entries into the generated agent
file. If composition happens, the generated agent *is* the human-readable
rendering, and the authored form does not need to carry that duty. The two
decisions were in tension and only one of them can be load-bearing.

**The citation-drift argument was factually wrong.** It cited four Cook
citations of which two read only "Cook, thesis 8", and called that drift at
three weeks old. Reading the files rather than the extracted lines shows
`sre.md` establishes the full work in its first Cook citation and short-forms
afterward, which is ordinary practice within a document, and `support-lead.md`
names the title independently. Every role file is already self-sufficient. The
observation that motivated a central registry was an artifact of grepping
`Source:` lines out of the documents that give them context.

## Decision

**Author entries as JSON-LD.**

The record model was designed as schema.org `LearningResource` with a decided
namespace. Authoring in that model removes the mapping step between the
authored form and the interchange form, and with it the class of bug where the
two disagree. The alternative left the graph as a derived shape that nothing
generated, which is a decision to defer the model indefinitely while claiming
to have adopted it.

The corpus is graph-shaped in ways prose does not hold. `teaches` joins entries
to competency terms, `flow:layer` distinguishes baseline from experience,
`audience` binds an entry to a role, and `flow:source` is multi-valued. During
the pilot, verifying the `teaches` join required an ad-hoc script that
normalized Markdown line wrapping before it could compare a term reference to
an entry title — and its first run reported four false mismatches that were
purely line-wrap artifacts. Structure that needs a whitespace-normalizing
parser to check belongs in the format.

Entry prose stays prose: the five parts remain authored sentences, carried in
`abstract`, `flow:trigger`, `flow:requiredBehavior` and `flow:failureMode`. The
wording is what changes model behavior and it is not abbreviated by the move.

**Each role owns its own entries and its own citations.**

Entries live in `scaffolds/default/expertise/<role>.jsonld`, self-contained,
with citations written in the entry rather than referenced out to a shared
registry. There is no central registry; the earlier revision's `sources.md` is
withdrawn.

Repetition across roles is expected and correct, not redundancy to be
factored out. A work teaches different things to different roles: Croskerry's
availability bias is a triage discipline for `support-lead` and his
"not yet diagnosed" category is a definition discipline for `business-analyst`.
These are different knowledge from one source, and the entry that carries each
belongs to the role that needs it. A shared registry would make the shape of
the corpus imply otherwise — that a work is a single asset roles borrow —
and would couple three role files through a fourth for no benefit that the
files' self-sufficiency does not already provide.

The same holds within a role. `support-lead` cites Croskerry four times and
`sre` cites Cook three times, each at a different pinpoint. That is one source
yielding several distinct pieces of knowledge to one agent.

This does not weaken the leakage test. That test asks whether two entries share
a source *and* a `flow:requiredBehavior`; a repeated source with distinct
required behavior is exactly what a well-mined source looks like.

**Pinpoints attach to the entry as `flow:locator`.**

One role cites one work at several pinpoints — Cook appears in `sre.md` as
theses 3/7/15, as thesis 8, and as thesis 14. A locator on the cited work
cannot represent that, and `citation.description`, the alternative the handoff
named, attaches to the work and has the same defect. Per-role ownership does
not change this, since the collision occurs inside a single role file.

`citation` carries the work's identity; `flow:locator` carries the part of it
this entry draws on. Where an entry cites two works at once — Cook's thesis 8
with Allspaw on first and second stories — `flow:source` is a list and each
member carries its own locator.

### Worked example

One entry, in the shape this ADR approves. The role file is a `@graph` of
these, sharing one `@context`.

```json
{
  "@id": "flow:entry/support-lead/discount-recent-failure-mode",
  "@type": "LearningResource",
  "name": "Discount the failure mode you saw most recently",
  "audience": { "@type": "Audience", "audienceType": "support-lead" },
  "flow:layer": "baseline",
  "abstract": "The causes that come to mind fastest are the ones seen most recently, not the ones most likely here. Recent volume crowds out rare failures that present the same way.",
  "flow:trigger": "The symptom matches a pattern from a recent incident, release, or cluster of tickets.",
  "flow:requiredBehavior": "State the recent case you are matching against and the observation that distinguishes this report from it. Take that observation before acting on the match.",
  "flow:failureMode": "Applying the current known-issue workaround to a report that merely resembles it, which buries a distinct defect inside a resolved one.",
  "flow:source": [
    {
      "citation": {
        "@type": "ScholarlyArticle",
        "author": "Pat Croskerry",
        "name": "From Mindless to Mindful Practice — Cognitive Bias and Clinical Decision Making",
        "isPartOf": "New England Journal of Medicine",
        "datePublished": "2013",
        "pagination": "2445-2448",
        "sameAs": "https://doi.org/10.1056/NEJMp1303712"
      },
      "flow:locator": "availability"
    }
  ],
  "teaches": [
    { "@type": "DefinedTerm", "@id": "flow:competency/test-a-familiar-pattern-match-before-acting" }
  ]
}
```

Note `flow:locator` sitting beside `citation` rather than inside it: the
sibling entry citing Croskerry on diagnosis momentum repeats the same
`citation` object with a different locator, and that repetition is the
expected shape rather than a normalization failure.

## Alternatives considered

- **Authored Markdown with a derived JSON-LD envelope**, following the
  archive's precedent of authored prose and generated structure. Rejected
  above. The precedent is real but the cases differ: archive records are
  written during a run by a lane, as narrative, and their structure is
  extracted; expertise entries are authored deliberately against a model that
  already exists.
- **Markdown with YAML frontmatter per entry.** Rejected. It carries the
  metadata but not the graph — a `teaches` value in frontmatter is a string
  that resolves by convention, which is the problem JSON-LD solves.
- **A central id-keyed source registry.** Rejected above.
- **One file per entry.** Rejected for now: seventeen entries across three
  roles read better as three role documents, and the role file is the unit
  that sync composes and that a user's experience layer overlays.

## Consequences and owned follow-up

- Human review of the authored corpus becomes review of JSON. The composed
  agent file remains the readable rendering, so this cost falls on the author
  and reviewer of an entry, not on someone reading a role. Diff quality on
  reworded prose inside JSON strings is worse than on Markdown and is the real
  price of this decision.
- Sync composition is unimplemented and gates the move. Until it exists the
  entries stay inline in the agent files, so this ADR describes the target and
  does not move them. Whoever owns the CLI owns the composition point, the
  baseline/experience union, and source attribution in composed output.
  Experience entries rank above baseline and do not suppress it.
- Composition now has a second duty: rendering JSON-LD entries as the
  five-part Markdown shape the agents currently carry. The pilot's validation
  evidence is against that rendered shape, so the renderer's output should
  match it closely enough that the result still applies.
- The `teaches` join is unblocked and becomes a real edge rather than a
  recorded convention.
- Retrieval remains out of scope at seventeen entries. If built, ADR 0004's
  ranker applies — BM25 over a transient merged corpus, not a vector index.
- The bibliography still carries the rejected `https://flow.dev/ns#` in its
  JSON example, and neither it nor the discovery handoff is in the repository.
  Reconciling the pasted design documents against this ADR is open.

## Evidence

The citation counts and per-file self-sufficiency were read from the three
agent files at v0.26.0. The line-wrap false positives are from the pilot's
vocabulary cross-check. No experiment was run for this decision: it rests on
the record model already chosen, on the structure the corpus carries, and on
the ownership argument above.
