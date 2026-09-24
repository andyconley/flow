# Acceptance criteria: First execution contract and Shaper charter

Status: Approved with the definition by Andy Conley on 2026-09-19. These criteria define the first execution slice; they are not evidence that it is implemented.

1. A declared Codex assignment with a missing or unknown required capability is refused before launch; a confirmed assignment can be correlated to one unique attempt and the exact approved brief/manifest inputs.
2. For one completed worker attempt in an isolated worktree, the coordinator/provider-side receipt identifies work, assignment, provider, attempt, runtime/session, baseline commit, resulting commit, declared outputs, independently observed changes, validation results, and evidence references. A reviewer can resolve those references without worker chat.
3. A partial, failed, cancelled, or interrupted attempt retains an attributable diagnostic receipt with no-commit or last-safe-state information, reason, unresolved work, and safe next action. It cannot be accepted as a successful changed-work handback.
4. Missing/mismatched output, commit, input identity, scope disposition, or validation evidence prevents a successful handback. A worker-authored or tampered receipt, unaccounted committed/uncommitted/untracked change, symlink/path escape, or unauthorized delta also blocks success. The failure is machine-readable and leaves the existing lifecycle state unchanged when its gate refuses the transition.
5. The Shaper charter identifies outcome, boundaries, constraints, acceptance, delegated authority, prohibited decisions, escalation, and decision owner, and references approved artifacts. A replacement coordinator can identify which changes require engineer approval.
6. Receipt and charter detail do not become authoritative lifecycle state in `run.json`; existing orchestration identities, claim provenance, reconciliation, and handback validation remain the integration points.
7. Representative secret-bearing command, environment, log, validation, path, and failure data are absent from the durable receipt and reviewable evidence while diagnostic outcome and bounded references remain available.
8. The contract can represent a future routed attempt with distinct provider, routing deployment/policy, requested profile/model, and observed underlying model (or explicit unknown), without making a router mandatory for the first Codex worker.
9. A worker that requires broader permissions returns a blocked receipt and escalation request without an interactive unattended approval or self-expansion of scope.
10. The charter records shaping/aligned status and its authorization provenance; each required validation result identifies the acceptance criterion or gate it addresses.
