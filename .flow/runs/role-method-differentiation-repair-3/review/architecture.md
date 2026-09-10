# Adversarial architecture review: three-role expertise expansion

- Reviewer: solution-architect
- Date: 2026-09-09
- Verdict: Needs one preservation clarification before approval; capability
  boundary and direct route to planning are otherwise sound

## Evidence inventory

### Inspected

- Draft definition and acceptance criteria for repair-3.
- Architecture challenge, product, requirements, testability, candidate-source,
  and archive-retrieval research notes.
- ADR 0008, `docs/architecture.md`, `docs/file-structure.md`, the current and
  `HEAD` composition manifests, PM/QR role bodies and corpora, competency
  vocabulary, renderer tests, and the relevant working-tree diff.
- Repair-2 requirements, frozen manifest, score, formal review, reconciliation,
  and handoff, plus the original expansion result.

### Partially evidenced

- The PM/QR additions are uncommitted and their body changes are small, so
  restoring the `HEAD` role contracts and removing their untracked corpora is
  locally reversible. Planning still must enumerate every generated,
  documentation, vocabulary, and test surface that carries the eight-role
  inventory.
- The draft promises to preserve both generations of failed evidence, reviews,
  and source-verification records. Its digest criteria name evidence trees but
  do not define whether run-level research and review artifacts belong to those
  trees.

### Checked and absent

- No accepted decision requires every role with a source-backed JSON-LD file to
  remain composed.
- No current consumer or schema requires a two-axis status contract for this
  narrowed release.
- No retrieval, routing, storage-format, overlay, merge, or renderer redesign is
  needed for the proposed removal.

## Findings

### Important: preservation scope is narrower in acceptance than in the requirement

Requirement 4 preserves the original and repair-2 designs, raw responses,
manifests, scores, reviews, and source-verification records. Acceptance
criteria 5 and 6 require byte identity for “both prior PM/QR evidence
generations” and “failed PM/QR evidence trees,” but neither names the included
paths or states whether run-level artifacts such as
`.flow/runs/role-method-differentiation/research/source-verification.md` and the
formal reviews are inside the protected set.

This ambiguity matters because the frozen response envelopes live under
`docs/evidence/`, while review and source-verification evidence also lives
under the prior `.flow/runs/` tree. A plan could hash only the two
`docs/evidence/` directories, delete or rewrite a run-level record, and still
appear to satisfy criteria 5 and 6.

- **Required disposition:** Before approval, make one acceptance criterion name
  the complete preservation inventory by path or point to a start-receipt
  manifest that enumerates every protected artifact required by requirement 4.
  The final receipt must compare the same inventory. New repair-3 receipts may
  be added outside the protected set; no protected artifact may be reformatted
  merely to add a label.
- **Why this is definition work:** The protected evidence boundary is part of
  the promised outcome. Planning may choose the hashing command and receipt
  format after the definition identifies what must survive.

### No finding: removing active PM/QR content does not violate ADR 0008

ADR 0008 decides the authored JSON-LD format, inline citation/pinpoint shape,
and per-role ownership of expertise entries. Its scope explicitly does not
approve retrieval or sync composition, and it contains no admission rule saying
that a source-backed corpus must ship or remain active after failed behavioral
evidence.

The draft preserves ADR 0008 for the six remaining composed roles and retains
the PM/QR authored entries and source evidence historically. Removing the two
uncommitted corpus files, competency edges, `generation_mode = "composed"`
declarations, and executable role-body additions therefore changes release
membership, not the storage architecture or ownership boundary.

- **Disposition:** Honor ADR 0008 as applicable precedent, with no conflict and
  no supersession. Do not edit ADR 0008 to record this run-local admission
  decision.
- **Guard:** Release documentation should say PM/QR were removed from this
  active expansion because the frozen gate failed. It should not generalize
  that result into a framework-wide policy that all failed or unproven methods
  must be removed. A general admission policy would be a separate durable
  capability decision and could warrant solutioning and an ADR.

### No finding: the removal is bounded cleanup, not avoidable architecture churn

The current diff shows PM and QR were added to the composed manifest, received
one new role-body method each, added two new JSON-LD corpora and competency
terms, and expanded tests and documentation from six to eight composed roles.
At `HEAD`, both roles use their unchanged verbatim contracts and are absent from
the composed cohort. Returning those exact surfaces to the six-role state is a
small, reversible subtraction aligned with the evidence-supported claim.

There is necessary update work in the manifest, role bodies, corpus/vocabulary,
tests, architecture/file-layout documentation, and evidence summaries. That is
claim reconciliation, not a new composition design. Keeping failed methods
active solely to avoid those edits would create a misleading runtime/product
boundary: users would receive prompt content that the release explicitly
declines to admit.

- **Disposition:** Accept active removal as the minimum coherent implementation
  of the selected three-role release, subject to preservation receipts before
  mutation.
- **Guard:** The plan should restore PM/QR role bodies from the exact frozen
  control/`HEAD` sources and delete only the uncommitted active corpus and
  vocabulary surfaces. It must not derive replacements by manually editing the
  frozen treatment bodies.

### No finding: the draft may route directly to planning

The selected approach has one clear implementation shape: retain the three
passing additions, restore PM/QR active surfaces to the pre-expansion state,
update exact cohort assertions and release language, preserve evidence, and
validate both adapters. No unresolved technical option affects storage,
composition, ownership, or runtime integration.

The release-note compatibility concern is a bounded inventory and wording task.
The criteria already require current documentation and evidence summaries to
describe three added and six total composed roles. Planning can locate those
consumers and map each to an edit and validation without choosing a new
architecture.

- **Disposition:** Route to `flow-plan` after explicit engineer approval and
  the preservation-scope clarification. This follows
  `standards/definition.md` **Routing** because the requirements and likely
  implementation path are clear.
- **Escalation condition:** Route to `flow-solution` only if planning discovers
  a machine-consumed release/status contract that cannot represent a narrowed
  cohort without schema change, or if the scope reopens a general two-axis
  admission policy. Neither condition is currently evidenced.

## Prior-decision dispositions

### Repair-2 all-five release relationship

The prior approved definition says the combined five-role release is eligible
only if both PM and QR pass. They did not, and the formal review blocked
acceptance. The repair-3 draft does not reinterpret that result; it proposes a
new three-role boundary.

- **Disposition:** Explicit engineer approval of repair-3 supersedes only the
  prior all-five *release relationship*. It does not supersede or weaken any
  repair-2 score, stopping rule, preservation requirement, or failure label.
  Until that approval, the draft remains unapproved and neither the all-five nor
  three-role release is authorized.

### ADR 0008

- **Disposition:** Applicable and honored. The retained active corpora continue
  to use its JSON-LD, citation, pinpoint, and role-ownership shape. Historical
  PM/QR entries retain that provenance. No ADR change is required because
  composition admission was outside ADR 0008's decided scope.

### Archive retrieval

- **Disposition:** No ranked precedent was returned. The active selection
  remains unavailable, and the current decisions above come from manually
  inspected project artifacts outside that selection. The retrieval miss does
  not authorize removal, block it, or create a substitute scorer.

## Approval readiness

After the protected evidence inventory is made explicit, the draft is
architecture-ready for engineer approval. Its removal boundary is compatible
with ADR 0008, preserves repair-2 semantics, avoids a premature general status
architecture, and is concrete enough for `flow-plan`.

## Recheck

The preservation clarification is resolved. Revised requirement 4 and
acceptance criteria 5 and 6 bind preservation to
`evidence/preservation-inventory.json`; that per-file inventory includes both
historical evidence roots, the complete prior definition/review run, the formal
reviews, and `research/source-verification.md`. The start receipt hashes the
inventory itself, and the final receipt must compare the same paths and reject
missing, replacement, or mismatched files.

No architecture finding remains open. The narrowed boundary still honors ADR
0008, leaves the two-axis policy deferred, and has one clear implementation path
to `flow-plan`. Only explicit engineer approval remains: it must authorize the
three-role release, active PM/QR removal, and supersession of repair-2's
all-five release relationship without weakening repair-2 evidence or scores.
