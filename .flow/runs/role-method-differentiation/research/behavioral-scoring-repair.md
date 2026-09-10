# Behavioral scoring: repair-2

## Decision

Both repaired role gates fail under the stopping rule frozen before execution.
The eight Claude Code records completed successfully with parity inside every
treatment/control pair, and both treatment counter-cases behaved safely. The
primary comparisons did not show the required treatment-only behavior.

## Product manager

| Criterion | Treatment | Control | Basis |
| --- | --- | --- | --- |
| `PM-P1` classify all three time-value shapes | pass | pass | Both identify compliance as a cliff/deadline, onboarding as gradual erosion, and dashboard value as flat. |
| `PM-P2` compare delay cost divided by duration for every option | fail | fail | Treatment rejects the required compliance ratio; control never calculates or explicitly compares all three ratios. |
| `PM-P3` sequence from that comparison and reject importance-only order | pass | pass | Both choose compliance, onboarding, dashboard and explain why the largest stated value does not go first. |
| `PM-C1` avoid invented urgency | pass | pass | Both decline to manufacture a ranking for flat, undifferentiated options. |

Treatment fails one primary predicate, and control satisfies two. The strict
product-manager gate is false. The fixture also omits an initial onboarding
benefit, so the total captured-value amounts asserted by both arms are not
derivable. That defect does not change any frozen predicate score.

## Quality reviewer

| Criterion | Treatment | Control | Basis |
| --- | --- | --- | --- |
| `QR-P1` state the plausible database-constraint explanation | pass | pass | Both identify the explanation that the constraint rejects the value before commit. |
| `QR-P2` rule it out with schema and observed persistence | pass | pass | Both use the absent value-set constraint and the persisted `turbo` read. |
| `QR-P3` file Critical only after completing that chain | fail | fail | Both declare the Critical before presenting the alternative and discriminating evidence. |
| `QR-C1` keep the unresolved counter-case below Critical | pass | pass | Both request the missing evidence and avoid a Critical. |

Treatment fails one primary predicate, and control satisfies two. The strict
quality-reviewer gate is false.

## Evidence and stopping rule

- **Observed:** all eight JSON envelopes report success; all immutable response
  hashes match
  `docs/evidence/role-method-differentiation/repair-2/execution-results.json`;
  prompt/settings parity holds for every pair; the independent quality reviewer
  supplied criterion-level scores.
- **Read:** `manifest.json` froze the bodies, designs, prompts, provider
  settings, parity rules, and role-pass formula before any run.
- **Disposition:** preserve `repair-2` as failed. Selective reruns and rescoring
  are forbidden. A changed method, prompt, fixture, or rubric starts a new
  versioned envelope.

The machine-readable score is
`docs/evidence/role-method-differentiation/repair-2/results.json`. Architect,
test-engineer, and lead-developer retain their prior passes. Product-manager and
quality-reviewer remain failed, so the combined five-role gate is false.
