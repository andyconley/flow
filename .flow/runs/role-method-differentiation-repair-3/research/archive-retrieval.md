# Research: prior archive decisions for repair-3

- Owner role: solution-architect
- Date: 2026-09-09
- Confidence: High for the retrieval result; medium for manually inspected local evidence

## Question

What current archived decisions constrain the next product-manager and
quality-reviewer differentiation attempt?

## Method and sources

- Ran `flow archive search "product-manager quality-reviewer role method
  behavioral differentiation repair" --lane define --json` once at lane entry.
- Active selection: `321754eda89abf939c1f47c9078a57c15ad5b926183b02d940c6169e28df9d57`.
- Ran `flow doctor` after retrieval reported `unavailable`.
- Manually inspected the prior run's approved requirements, acceptance criteria,
  frozen repair-2 results, and formal review outside the active selection.

## Findings

- Retrieval returned exit 4 and no ranked hits because the ready project source
  has `no_index`; its actionable remedy is `flow index rebuild` in the project.
  `flow doctor` confirms FTS5 is available, so this is missing index state rather
  than a scorer fallback.
- The unavailable result is not evidence that no relevant decision exists.
- Manual local evidence records three binding constraints: preserve repair-2 as
  failed evidence, do not selectively rerun or rescore it, and create a new
  versioned envelope for any changed method, prompt, fixture, or rubric.
- Manual local evidence also shows that a new method must add behavior absent
  from the unchanged role body; competent generic reasoning already supplied
  much of the prior product and quality behavior.

## Implication for requirements

- Repair-3 must use a separate evidence envelope and retain all earlier evidence.
- Candidate methods must be screened against the unchanged role contracts before
  they become requirements.
- No retrieved decision is available to create a conflict or applicability
  disposition. The manually inspected constraints remain identified as outside
  the active retrieval selection.

## Open follow-ups

- Rebuild the archive index only as separate maintenance; do not rerun automatic
  retrieval or replace the active selection during this definition.
