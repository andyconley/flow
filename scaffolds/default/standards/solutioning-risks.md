# Solutioning Risks

This standard defines how risks, dependencies, and blockers are surfaced, owned, and mitigated during solutioning.

## Three categories

Distinguish these — they have different time horizons and management cadences.

- **Blocker** — an immediate obstacle stopping work right now (missing resource, unresolved question, pending approval, broken environment).
- **Dependency** — a cross-team, system, or vendor need that affects timeline or deliverable.
- **Risk** — an uncertainty that could affect scope, resources, or technical feasibility.

## The four-step pattern (ICOM)

Apply to all three categories:

1. **Identify** — surface in standups, refinement, design sessions, or explicit risk reviews.
2. **Communicate** — share openly, categorize, escalate to the right stakeholders.
3. **Own** — assign a specific person responsible for tracking and resolving. *Without an owner, it doesn't exist as a managed concern.*
4. **Mitigate** — concrete plan. Root-cause analysis for blockers; time buffers and alternative paths for dependencies; phased rollouts or extra resourcing for risks.

## In solutioning output

The risks section of a solutioning artifact is not a list of things you noticed. Each entry has:

- The risk, dependency, or blocker stated concretely.
- Likelihood and impact (qualitative is fine).
- **Owner** — named person.
- **Mitigation** — concrete plan, or "accepted, no mitigation" with explicit rationale.

If you can't name an owner, the risk isn't ready for solutioning to close — either get an owner or reclassify as an open question for follow-up.

## Bug severity vs priority

Often conflated; keep them separate.

- **Severity** describes user impact (Blocker / Critical / Major / Minor). Fixed by what the bug breaks for the user, not by deadline.
- **Priority** describes business urgency — when we work on it given everything else.

Business deadlines change priority. Severity is fixed by impact. A Major-severity bug can be deprioritized; a Minor-severity bug doesn't get upgraded just because someone is mad. Every bug ticket carries both, named explicitly. Bug reports include reproduction steps, affected scope, evidence (logs, screenshots, metrics), and any workaround with its risk notes.

## Embedding in the workflow

- **Inception** — surface dependencies and risks while defining the problem.
- **Definition / Solutioning** — break work into clear tasks; prioritize dependencies; create mitigation plans.
- **Implementation** — regular check-ins with dependency owners; adjust as the project evolves.
- **Release** — feature flags and phased rollouts to reduce blast radius; post-release review.

## Tracking signals

- **Blocked time** — percentage of in-flight tasks stuck on a blocker.
- **Dependency resolution time** — how long it takes to clear dependencies.
- **Risk mitigation rate** — percentage of identified risks handled effectively.

## Relevant principle

Unmanaged blockers, dependencies, and risks are the most common reason delivery slips. The discipline isn't to list them — it's to own and mitigate them. A risk without an owner is decoration.

## Related standards

- `solutioning-criteria.md` — criteria types every work item carries.
- `solutioning-decisions.md` — decision criteria for solutioning.
- `incident-management.md` — distinct from risks (incidents are post-event; risks are forward-looking).
