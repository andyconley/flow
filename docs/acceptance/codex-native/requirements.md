# Requirements: reject an empty greeting name

Workflow: `native-acceptance` · Stage: `define` · Status: definition draft, not lifecycle approval.

## Problem Statement
- What: `greeting(name)` currently formats an empty name into a greeting instead of rejecting it.
- Who: callers of the fixture function.
- Why now: the disposable Codex-only acceptance task explicitly requests this behavior change.

## Users and Workflows
- Primary persona: a caller supplying a name to `greeting`.
- Current workflow: every supplied value is interpolated into `Hello, {name}!`.
- Future workflow: an empty string is rejected; non-empty string greetings retain their existing format.

## Evidence and Definition Research
- Inspected `fixture.py:1-2`: the function contains only `return f"Hello, {name}!"`, with no validation. Static inspection establishes that `greeting("")` returns `"Hello, !"` and `greeting("Ada")` returns `"Hello, Ada!"`. These are source-derived observations, not executed test results.
- `task.md:1` and the stage request establish the requested change and the two-artifact-only boundary.
- No applicable project `AGENTS.md`, `.flow/PROJECT.md`, `standards/research-evidence.md`, or `templates/research-note.md` was found at the checked project paths. Research evidence is retained here within the authorized outputs; no external research was performed.
- Confidence: high in current behavior and the empty-string requirement; error details and broader invalid-input semantics remain unspecified.

## Scope
- In scope: define rejection of the exact empty string and preserve non-empty string output.
- Out of scope: implementation, test-file changes, trimming, general type validation, infrastructure, and changes outside the two requested artifacts.
- Constraints: use only this fixture project and existing permissions. Flow owns lifecycle approvals. Do not modify `run.json`, `events.jsonl`, or runtime session storage.

## Requirements
- R1: `greeting("")` must signal rejection rather than return a greeting.
- R2: non-empty string inputs must retain the exact existing `Hello, {name}!` output, including supplied whitespace and Unicode.
- R3: rejection must be observable to the caller. Proposed contract: raise `ValueError`; exception type and message remain subject to definition resolution.
- User story: as a caller, I want an empty name rejected so that I can distinguish invalid input from a successful greeting.
- Acceptance criteria: see `acceptance-criteria.md` in this directory.

## Risks and Open Questions
- Assumption: “empty” means the zero-length string, not whitespace-only strings or other falsy values.
- Open question: should rejection raise `ValueError`, and is a particular error message required? Proposed default is `ValueError` with no exact-message requirement.
- Open question: should whitespace-only strings or non-string values also be rejected? They are outside this slice pending an explicit scope decision.
- Risk: broad falsy checks or trimming could unintentionally change existing behavior beyond the requested empty-string case.

## Delivery Slices
1. Current stage: retain requirements and reviewable acceptance criteria in the two authorized artifacts.
2. After Flow authorization and resolution of the rejection contract: implement empty-string rejection and verify it alongside preserved greeting behavior.
3. No follow-on expansion is requested; broader validation requires a separate scope decision.
