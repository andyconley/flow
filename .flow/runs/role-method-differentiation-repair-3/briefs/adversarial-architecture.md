# Adversarial review brief: architecture

## Task

Challenge the draft choice to remove active PM/QR methods and avoid a two-axis
status architecture. Test boundary fit with ADR 0008, evidence preservation,
composition semantics, and the recommended direct route to planning. Write only
to `.flow/runs/role-method-differentiation-repair-3/review/architecture.md`.

## Evidence inventory

### Already exists

- Draft definition/criteria and architecture research note.
- ADR 0008, architecture/file-layout docs, composition manifest, corpora, and
  renderer tests.
- Frozen repair-2 evidence and formal review.

### Partially covered

- Provenance and behavior are distinct evidence dimensions, but Flow has no
  general status contract for them.
- Removing uncommitted PM/QR active content is locally reversible; release-note
  compatibility still needs planning.

### Checked and genuinely absent

- No existing decision permits provenance-only methods to remain in active
  prompts after failed behavioral admission.
- No need for retrieval, routing, storage, or renderer redesign is evidenced.

### Search method

The coordinator inspected the relevant architecture standards, ADR, manifests,
rendering path, working-tree diff, and both failed evidence envelopes.

## Required output

- State whether removal violates an existing boundary or creates avoidable churn.
- Decide whether solutioning is necessary or planning is sufficient.
- Give explicit dispositions for the prior all-five relationship and ADR 0008.
