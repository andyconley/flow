# ADR 0008: Author expertise entries as Markdown with referenced sources

- Status: accepted
- Date: 2026-09-07
- Decision owner: repository owner
- Related work: agent expertise corpus, pilot roles business-analyst, sre, support-lead
- Scope: authored storage format, citation shape and source locators; retrieval, the derived envelope and the two-layer merge mechanism are named here but not approved by this ADR

## Context

The expertise capability shipped its pilot in v0.26.0: seventeen five-part
entries across three roles, a competency vocabulary, and a two-arm validation
record. The bibliography and provenance handoff left three questions open and
explicitly directed that they be settled in solutioning rather than defaulted —
storage format, whether citations are inline or by reference, and where a
source pinpoint lives. The namespace was already decided as
`https://andyconley.github.io/flow/ns#` bound to prefix `flow`.

The record model in the bibliography is schema.org `LearningResource`, which
implies a JSON-LD document. Nothing in Flow reads or writes JSON-LD today; the
only occurrences of `@context` in the tree are Python decorators. The entries
are currently authored as Markdown inside the three agent files and reach the
model by being inlined into the generated agent whole, with no selection step.

Flow already has a comparable subsystem, and its precedent is the relevant
evidence. Archive records are authored as Markdown — `archive.md`,
`scout-summary.md`, `HANDOFF.md` — and located by
`heading:<heading>:<occurrence>` selectors pinned with a SHA-256 digest. The
JSON envelope is derived, the projection is cached, and the query corpus is
assembled transiently and never repaired on reads. Authored prose is
authoritative; structure is generated from it.

Two properties of the current corpus bear on the citation questions. It has
seventeen citations over six distinct works: Croskerry seven times, Cook four,
Allspaw and Klein twice each, Levitt and Fitzpatrick once each. And the same
work carries a different pinpoint in every entry that cites it — Cook appears
as "theses 3, 7, and 15", as "thesis 8" twice, and as "thesis 14".

Drift is already present. Of the four Cook citations, two name the work and its
revision year and two read only "Cook, thesis 8", relying on a neighbouring
entry for the work's identity. The corpus is three weeks old.

## Decision

**Author entries as Markdown. Do not author JSON-LD.**

The five-part entry shape is the authored artifact. It is written by a person,
read by a person reviewing a role, and read by the model verbatim. JSON-LD is
retained as the *derived* interchange shape for the record model, generated
when something consumes it, on the same footing as the archive's envelope:
derived, disposable, never hand-maintained. Nothing consumes it today, so
nothing generates it today.

**Move the authored entries out of the agent files into
`scaffolds/default/expertise/<role>.md`, and have sync compose them into the
generated agent.**

This is the decision with consequences beyond formatting. A generated agent
file is replaced wholesale on `flow sync`, which is correct for baseline
content and fatal for the user-owned `experience` layer the bibliography
requires. Entries can only carry a durable user layer if the agent file is a
composition target rather than the place the entries live. Composition
preserves the property the pilot depends on — entries are in context whether or
not a query would have matched them — while making a merge point exist.

**Cite by reference, not inline.** Works live in
`scaffolds/default/expertise/sources.md` as an id-keyed registry carrying
author, title, publication, year and, where it exists, a DOI or URL. An entry
names `Source:` by id.

Seven Croskerry citations restating one journal reference is seven chances to
disagree with each other, and two of four Cook citations have already dropped
the work's identity. Reference storage also serves the distribution
constraint: the baseline corpus ships with Flow, so credit for origin must be
accurate in one auditable place rather than seventeen.

**Pinpoints live on the entry as `flow:locator`, not on the work.**

This follows from the corpus rather than from taste. A pinpoint identifies the
part of a work *this entry* draws on; Cook's theses 3/7/15, 8 and 14 are three
different locators into one registry record. A locator on the work cannot
represent that, and `citation.description` — the alternative named in the
handoff — attaches to the cited work, so it has the same defect.

`flow:source` is a list. Two entries legitimately cite two works at once
(Cook's thesis 8 with Allspaw on first and second stories), and flattening
that to a string reintroduces the parsing the registry exists to avoid.

The authored line therefore reads:

```
- Source: cook-how-complex-systems-fail (thesis 8); allspaw-blameless-postmortems
```

with the parenthesised locator optional and the bare id sufficient for a work
cited whole.

## Alternatives considered

- **JSON-LD as the authored format.** Rejected. The entry's value is its
  wording — the counter-tests turned on phrases like "do not ask 'were you
  opening it directly in Excel?'" — and authoring that inside JSON string
  values makes review harder for no gain while nothing consumes the graph.
  Retained as the derived shape.
- **Markdown with YAML frontmatter per entry.** Rejected for the entry itself:
  seventeen entries would become seventeen files, and the five-part shape is
  already a stable structure a parser can read. Frontmatter remains the
  obvious carrier for the registry and for per-file layer attribution if the
  merge implementation wants it.
- **Keep entries inline in the agent files.** Rejected because it forecloses
  the experience layer, which is the half of the corpus model that makes the
  capability worth building. Inlining as a *delivery* mechanism is retained.
- **Citations inline.** Rejected on the observed drift above.
- **Pinpoint in `citation.description`.** Rejected: attaches to the work, and
  one work carries several pinpoints.
- **A locator syntax mirroring the archive's `heading:<heading>:<occurrence>`
  selector with a content digest.** Rejected for external works — Flow does not
  hold Cook's text and cannot digest it. The archive's selector addresses
  content Flow owns; a citation locator addresses content it does not.

## Consequences and owned follow-up

- Sync composition is unimplemented and is the gating work. Until it exists the
  entries must stay inline in the agent files, so this ADR describes the
  target and does not move them. Whoever owns the CLI owns the composition
  point, the baseline/experience union, and source attribution in the composed
  output. Experience entries rank above baseline and do not suppress it.
- The `teaches` join stays recorded vocabulary-side only. It was deferred
  pending this decision; it is now unblocked, and adding a `Teaches:` line per
  entry is mechanical.
- Retrieval remains out of scope and unjustified at seventeen entries. If it
  is built, ADR 0004's ranker applies: BM25 over a transient merged corpus,
  not a vector index. The `Source:` and `Use when:` lines are short and
  keyword-dense, which suits a lexical ranker.
- The registry must be created before the ADR's citation shape can be used.
  It is small and is delivered with this ADR.
- The bibliography still carries the rejected `https://flow.dev/ns#` in its
  JSON example, and neither it nor the discovery handoff is in the repository.
  Reconciling the pasted design documents against this ADR is open.

## Evidence

The counts above were taken from the merged pilot at v0.26.0 by extracting
every `- Source:` line from the three agent files. The archive precedent is
read from `cli/archive_extract.py`, `cli/archive_model.py` and
`cli/archive_query.py` as of the same release. No experiment was run for this
decision: it rests on Flow's existing precedent, on the citation counts, and on
the locator argument, which is structural rather than empirical.
