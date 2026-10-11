# Acceptance criteria: reject an empty greeting name

Workflow: `native-acceptance` · Stage: `define` · Status: proposed criteria, not approval or implementation evidence.

## Behavioral Criteria
| ID | Requirement | Input / action | Expected result |
| --- | --- | --- | --- |
| AC1 | R1, R3 | Call `greeting("")`. | Explicit rejection; no greeting is returned. Proposed assertion: `ValueError` is raised, pending resolution of the exception contract. |
| AC2 | R2 | Call `greeting("Ada")`. | Exactly `"Hello, Ada!"`. |
| AC3 | R2 | Call `greeting("A")` and `greeting("Zoë")`. | Exactly `"Hello, A!"` and `"Hello, Zoë!"`. |
| AC4 | R2 | Call `greeting(" Ada ")` and `greeting(" ")`. | Exactly `"Hello,  Ada !"` and `"Hello,  !"` under the proposed zero-length-only scope; no trimming. |

## Definition-stage Review Criteria
- Both requested Markdown artifacts exist and record scope, source evidence, assumptions, and unresolved questions.
- No implementation or test files are changed by this stage.
- Flow lifecycle and runtime storage remain untouched by this stage; artifact production does not approve work or advance the lifecycle.

## Evidence and Validation Status
- Actual evidence: inspected `fixture.py:1-2`, whose unconditional formatted return accepts an empty name; inspected `task.md:1`, which limits this stage to documentation.
- AC1 is unmet by the current source: it returns `"Hello, !"`. AC2–AC4 describe existing source-derived behavior to preserve.
- No behavioral tests were executed and no implementation is claimed. Later authorized implementation should provide test results for AC1–AC4 after the contract is resolved.

## Unresolved Questions
- Confirm the proposed `ValueError` rejection contract before treating that exception assertion as binding. Exact message matching is not currently required.
- Confirm that whitespace-only strings remain valid. AC4 reflects the narrow interpretation of “empty”; changing that interpretation requires corresponding requirements and criteria updates.
- `None`, numeric values, and other non-string inputs have no new validation contract in this slice. Decide separately if they need one.
