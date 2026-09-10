# Implementation current state: repair-3

- Work item: `role-method-differentiation-repair-3`
- Inspected: 2026-09-10
- Scope: approved production candidate, frozen evidence inputs, and required
  validation surfaces. No production or frozen evidence path was changed during
  this inspection.

## Observed baseline

- The checkout is on `main` at `2712f5f`; the planned
  `codex/role-method-differentiation-repair-3` branch has not yet been created.
- The tree contains the five-role candidate plus untracked immutable evidence
  roots and five role-owned corpus files. `.flow/memory/STATE.md` is separately
  modified; it is the pre-existing unrelated delta named in the approved plan
  and must remain unchanged and unstaged.
- `git diff --check` currently passes. This is a formatting observation only;
  it is not candidate acceptance evidence.
- The six retained source files listed in `evidence/start-receipt.json` match
  their recorded SHA-256 values: architect, lead-developer, and test-engineer
  role bodies and corpora. The receipt records the retained role/corpus hashes
  and must be treated as a read-only input.
- `evidence/preservation-inventory.json` contains 112 protected files. The two
  historical evidence roots currently contain 73 files, consistent with the
  receipt's 31- and 42-file tree counts; the remaining protected paths are in
  the prior run. Their per-file hashes still need the planned validator before
  production mutation.
- No current release summary exists at
  `docs/evidence/three-role-expertise-expansion/README.md`.

## Active candidate versus required final state

| Surface | Observed candidate | Required repair-3 state |
| --- | --- | --- |
| `scaffolds/default/flow.toml` | Eight roles have `generation_mode = "composed"`, including PM and QR. | Exactly six: architect, business-analyst, lead-developer, sre, support-lead, and test-engineer. Remove only PM/QR composition declarations. |
| `scaffolds/default/agents/product-manager.md` | Contains the new value-decay instructions. Its SHA-256 is `433e3e…`. | Restore exact bytes from `2712f5f` (the frozen control SHA-256 is `db45fa…`). |
| `scaffolds/default/agents/quality-reviewer.md` | Contains the alternative-explanation critical-finding instruction. Its SHA-256 is `b4a3bf…`. | Restore exact bytes from `2712f5f` (the frozen control SHA-256 is `4cd2d8…`). |
| `scaffolds/default/agents/lead-developer.md` | Contains the approved plan-depth additions and matches the start receipt. | Retain byte-for-byte. |
| `scaffolds/default/expertise/product-manager.jsonld`, `quality-reviewer.jsonld` | One active baseline corpus each. | Delete from the framework baseline only; do not touch any user overlay. |
| `scaffolds/default/expertise/competencies.md` | 18 terms, 23 entries, PM and QR terms/edges, and an eight-role coverage table. | Remove the two PM/QR terms and reverse edges; make all coverage and consistency claims 16 terms and 21 entries. |
| `tests/test_expertise_composition.py` | `COMPOSED_ROLES` is the eight-role set. Early tests require PM/QR executable boundaries and their replacement corpus entries. | Replace those assertions with the exact six-role cohort, PM/QR base-body equality and inactive-surface checks, retained evidence-map/hash/join/render checks, current-claim checks, and three mutation-sensitive guards. |
| `docs/architecture.md`, `docs/file-structure.md` | Both call the shipped composed cohort eight roles. | Describe three new roles and the exact six-role active cohort. |
| release-facing evidence | Historical roots are present and protected. | Add the new three-role summary outside protected roots; explicitly preserve PM/QR as failed historical evidence and base-only active roles. |

## Existing seams and dependencies

- The manifest's `generation_mode = "composed"` is the decisive activation
  seam. `sync.agent_body` is the shared renderer used by both adapters; test
  coverage can prove composition through that seam without changing the
  renderer.
- `cli/expertise.py` supplies corpus loading and forward/reverse vocabulary
  checks. The required repair is declarative: remove PM/QR data and flags,
  retain the three validated corpora, then extend the existing composition test
  module. No loader, schema, routing, or adapter change is indicated by the
  approved scope.
- `release-evidence-map.json` is the sole frozen mapping for architect,
  lead-developer, and test-engineer. Tests and the new summary should validate
  it rather than duplicate or reinterpret the historical pass/fail results.
- New run artifacts are hidden by the local exclude. They will require explicit
  `git add -f` when the accepted source is committed; that operation must never
  modify a protected file to make it addable.

## Required order

1. Run the read-only frozen-input validator and record the separate
   preimplementation verification. Fetch remote state and create the planned
   feature branch without resetting the candidate.
2. Restore PM/QR role files from `2712f5f`, remove their two baseline corpora,
   and remove only their manifest and vocabulary activation surfaces.
3. Update the focused composition tests so their direct oracle is the six-role
   set and their PM/QR assertions prove base-only operation. Add retained
   evidence and semantic-negation coverage before relying on the tests.
4. Update current architecture/file-layout text and add the new summary. Keep
   historical roots unchanged, even where they state the failed five-role
   history.
5. Create receipts and run the planned deterministic, mutation, adapter, and
   live-client validation against the resulting production digest `T`.

## Blocking contradiction check

No requirements contradiction was found. The observed candidate is deliberately
broader than the approved final state, and each discrepancy maps to an explicit
approved removal or restoration. The only implementation precondition is the
planned read-only validation of all frozen inventory paths before the first
production edit. It is not yet recorded, so implementation must perform it
before changing active surfaces.

## Risks to carry forward

- A simple role-count assertion can pass with the wrong cohort; use parsed set
  equality and assert PM/QR absence on every active surface.
- The PM/QR restoration authority is `2712f5f`, not their treatment bodies or
  any historical experiment output.
- Historical current-language searches must exclude the protected evidence
  roots. Those paths are expected to retain failed five-role wording.
- A change to any retained role or corpus invalidates its frozen hash and the
  supporting behavioral claim. A change after live proof invalidates the
  affected proof and must be rerun.
