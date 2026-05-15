# Solutioning Criteria

This standard defines the three criteria types every non-trivial work item carries through solutioning, and the tiered Definition of Done that gates completion.

## The three criteria types

Three distinct concepts that often get confused. Every non-trivial work item carries all three. They aren't interchangeable, and they're owned by different roles at different stages.

### Success criteria — the *why*

- Purpose: business outcome or KPI. Does the change actually solve the customer or business problem? Examples: user engagement, ROI, cycle time, defect rate, customer satisfaction.
- Set: during Inception/Definition (upstream of solutioning) by the Product Manager with leadership input.
- Measured: post-delivery, against the metric.

### Acceptance criteria — the *what*

- Purpose: specific conditions the deliverable must meet to be acceptable to stakeholders. Functional, user-facing.
- Set: during refinement or sprint planning by the Product Manager with the development team.
- Verified: at delivery, before the work transitions to "done."
- Format as a checkbox list so reviewers can tick items as they verify.

### Definition of Done — the *how good*

- Purpose: quality standard. What "complete" means at each level — code, tests, docs, deployment readiness.
- Set: by the team during sprint planning or retros.
- Tiered. Each level subsumes the one below.

## Tiered Definition of Done

### Ticket-level

- Code meets standards.
- Unit tests written and passing.
- Code reviewed and approved.
- Documentation updated.
- Feature demonstrated to stakeholders.

### Sprint-level

- All ticket-level items complete for every ticket in scope.
- Integration tests executed and passing.
- No critical bugs open.
- Stakeholder approvals received.

### Release-level

- All sprint-level DoD complete.
- Performance and regression testing complete.
- Release notes prepared and shared.
- Deployment procedures verified, including rollback plan.
- Outcome instrumentation in place to answer the Success criteria.

Projects with hardware-in-the-loop, simulation gates, or other domain-specific verification extend the release tier in their project overlay.

## How the three relate

- **Acceptance criteria** define what needs to be done for the feature.
- **Success criteria** evaluate whether the broader business outcome was achieved — measured later, in production.
- **Definition of Done** ensures the quality standard is met at every level before moving forward.

In a solutioning artifact, all three are named explicitly. Missing Success criteria is a sign the work is being shaped without a *why*; missing tiered DoD is a sign the validation strategy is underspecified.

## Relevant principle

Solutioning is incomplete if any of the three criteria are unstated. The criteria are how the work connects to outcomes (Success), to deliverables (Acceptance), and to quality bars (DoD).

## Related standards

- `done.md` — minimum DoD bar across the framework; this standard refines for solutioning.
- `solutioning-decisions.md` — decision criteria for choosing among options.
- `solutioning-risks.md` — risk, dependency, and blocker management.
