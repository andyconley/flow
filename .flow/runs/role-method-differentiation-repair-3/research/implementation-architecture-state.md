# Implementation architecture state

- Work item: `role-method-differentiation-repair-3`
- Owner role: architect
- Observed: 2026-09-10T10:53:43Z
- Verdict: approved architecture is implementable without a new boundary or ADR;
  the current tree is still the expected pre-narrowing state

## Current boundary state

The run is in `implementing` after approved definition and plan transitions.
The repository remains on local `main` at `2712f5f`, three commits ahead of
`origin/main` at `090b4df`. The planned branch
`codex/role-method-differentiation-repair-3` does not yet exist as the active
checkout. Create it at the current `2712f5f` lineage before the first
implementation mutation. Do not reset to `origin/main`: that would discard the
three accepted predecessor commits and would invalidate the frozen working-tree
context.

The active scaffold still expresses the rejected five-role candidate:

- eight roles declare `generation_mode = "composed"`, including
  product-manager and quality-reviewer;
- both PM/QR baseline corpus files still exist with one entry each;
- the PM/QR active role files do not equal their `2712f5f` base bytes;
- `competencies.md` still reports 18 terms and 23 entries and retains both
  PM/QR vocabulary edges;
- `docs/architecture.md` and `docs/file-structure.md` still describe eight
  composed roles.

These are implementation inputs, not new scope violations. The first active
slice must restore/delete/narrow them together to six composed roles, 16 terms,
and 21 entries. A partial state must not be synced into installed adapters or
described as the release result.

The three accepted additions are already at their frozen hashes:

| Surface | Observed SHA-256 |
| --- | --- |
| `agents/architect.md` | `3bbb040d5f3b038841d6fd9bde8e4f4d9c015c32317a5970a0d6d93eecd323b5` |
| `agents/lead-developer.md` | `2dc53fe1b1b5b671ddfddf1fc666dd6280d954282c34621cce626a375f22c513` |
| `agents/test-engineer.md` | `4581172d9e6c40130225f96513402af1a5a272b4b055471d359d9a2f935661b1` |
| `expertise/architect.jsonld` | `3993c9c5412944d41c83987c15ee6f9b3ebfe34485629b640bdd0ab52b015cfa` |
| `expertise/lead-developer.jsonld` | `6685816f415ef8c9544ecb49629848fa691232fa66781072b50f4d9d78feab7b` |
| `expertise/test-engineer.jsonld` | `640ed7cb566307393c4ff1588b9c3f6b8c65b22842f65af3c1fe84eb452e8a89` |

Keep those six files byte-identical while changing membership, vocabulary,
tests, and current documentation around them.

## Protected evidence boundary

The frozen inputs remain internally consistent at this inspection:

- `preservation-inventory.json` names 112 files, and every file exists with its
  recorded SHA-256;
- `release-evidence-map.json` names exactly architect, lead-developer, and
  test-engineer, and all six retained source hashes match;
- the historical evidence roots and the complete prior
  `.flow/runs/role-method-differentiation/` tree show no missing or mismatched
  protected file.

Implementation must validate these frozen documents without rewriting them.
Write observed implementation-entry results to the separate
`evidence/preimplementation-verification.json`, and write the final comparison
to `evidence/final-receipt.json`. Directory counts and aggregate tree hashes are
secondary; every listed path remains the acceptance authority.

The existing `.flow/memory/STATE.md` change predates repair-3. Its current file
SHA-256 is
`237cf7b512e212f586e9a8d283346244e51932f8cac06bea72e3ff8572d7a8ea` and
its current Git-diff SHA-256 is
`7583220b08f9c190602547158b82a6c66b6f8e7ba588c4d1af49e007f6d232cc`.
Record both as the unrelated-delta baseline, leave the file untouched and
unstaged, and exclude it from source commit `C` and the repair-3 evidence chain.
Use explicit-path staging; `git add -A` would violate this boundary.

## Generated adapter boundary

The canonical runtime inputs are `scaffolds/default/flow.toml`, role source
Markdown, role-owned JSON-LD corpora, and `competencies.md`. Claude and Codex
files under the user install are derived outputs. Do not edit or commit them.

After the active scaffold reaches the complete six-role state:

1. Run framework-only Claude and Codex syncs in isolated homes and inspect the
   actual generated files. Each generated test-engineer body must contain one
   `Define a test oracle with a concrete example` method; each PM/QR body must
   contain no generated Expertise section.
2. Run the real user syncs and both `--check` commands. User overlay corpora are
   outside this change and must not be deleted; PM/QR remain non-composed even
   if a user-owned corpus exists because the effective role declaration has no
   composed mode.
3. Run static smoke and the two-part doctor contract, then use fresh native
   Claude and Codex sessions for the live `test-engineer` proof. Static output
   cannot substitute for client consumption.

This uses the current merge and renderer boundaries as designed. No changes to
`cli/expertise.py`, `cli/sync.py`, `cli/render.py`, overlay rules, corpus format,
or model routing are justified.

## Release identity and operational boundary

The repository machinery supports the planned `T -> C -> R` chain, with one
stronger invariant than the plan's minimum wording:

1. **T** is the reviewed production-tree digest after deterministic, isolated
   adapter, doctor, and live-client proof. Formal review accepts T before the
   final source commit is created.
2. **C** is the committed and pushed accepted source. Every production path in
   C must match T; additions after review are limited to declared review/run
   evidence. `.flow/memory/STATE.md` remains unstaged and absent from C.
3. The `main` push starts the serialized four-job chain
   `analyze -> validate-candidate -> publish -> verify-published`. `analyze`
   binds its plan to exact source C; candidate validation and publication reuse
   that source and the plan/evidence digests.
4. **R** is semantic-release's generated release commit. The documented and
   implemented verifier requires R to have exactly one parent equal to C, not
   merely C somewhere in its ancestry. `C..R` changes exactly
   `CHANGELOG.md`, with the configured release subject and predicted tag.
   The public tag, GitHub release, `origin/main`, and refreshed local `main`
   bind to R.

The configured feature commit and its bounded `Release-Note:` trailer produce
release impact through the existing policy. Do not edit `CHANGELOG.md`, create
or retarget tags, publish manually, alter `release.config.cjs`, or change the
workflow. If remote `main` changes before merge, integrate it and regenerate
all proof affected by the new production tree before defining C.

Publication is the first costly recovery boundary. Before publication, use a
normal branch or source revert. After any public or uncertain write, preserve
remote objects and workflow artifacts, read current state, and follow
`docs/release-runbook.md`; repair forward through the same gated workflow.

## Exact implementation invariants

- Active composed set equals exactly `{architect, business-analyst,
  lead-developer, sre, support-lead, test-engineer}`.
- Vocabulary reports 16 terms and 21 entries; forward and reverse joins are
  complete for the six-role cohort.
- PM/QR role bytes equal `git show 2712f5f:<path>` and have no framework
  corpus, composed declaration, active vocabulary edge, or generated Expertise
  section.
- The six retained role/corpus SHA-256 values above remain unchanged.
- All 112 protected paths retain their recorded hashes, and failed PM/QR
  evidence remains visibly failed.
- The current release summary lives outside protected roots and claims three
  additions, six total composed roles, and no PM/QR behavioral pass.
- Three independent disposable mutations fail for PM/QR reintroduction,
  retained test-engineer removal, and semantic negation of the retained
  lead-developer obligation; each restores before the passing run.
- Both isolated generated adapters and both live clients show the intended
  state; unknown or inconclusive observations do not pass.
- Local doctor reports zero errors and the exact known-warning baseline; hosted
  candidate doctor remains a separate hard pass.
- Formal review accepts T before C exists; R's sole parent is C and its only
  changed path is `CHANGELOG.md`.

## ADR recommendation

No ADR is needed. Repair-3 narrows active membership under ADR 0008 and uses the
existing adapter and release contracts. Revisit architecture only if the work
expands into a provenance-only admission policy, composition/schema change,
renderer change, or a different publication identity model.
