## Problem Statement
- What: The `greeting` function currently accepts any input (including empty strings) and returns a generic greeting. It should instead reject an empty name.
- Who: Users/Developers calling the `greeting` function with invalid inputs.
- Why now: To prevent improper usage of the function and ensure that a valid name is provided for the greeting.

## Users and Workflows
- Primary personas: Developers interacting with the `fixture.py` API.
- Current workflow: Call `greeting("")`, receive `"Hello, !"`
- Future workflow: Call `greeting("")`, encounter an error/rejection (e.g., ValueError).

## Scope
- In scope: Modifying `greeting` in `fixture.py` to validate that `name` is not empty or whitespace.
- Out of scope: Changing the format of successful greetings; adding support for other types of validation (e.append, etc.); changing existing non-empty name behavior.
- Constraints: The implementation should stay within the bounds of a simple Python function in `fixture.py`.

## Requirements
- Goals: Ensure `greeting` only processes non-empty strings.
- Non-goals: Do not introduce external dependencies for validation.
- User stories: As a developer, I want the system to notify me when I provide an empty name so that I don't generate invalid greetings.
- Acceptance criteria:
    - Calling `greeting("Alice")` returns `"Hello, Alice!"`.
    - Calling `greeting("")` raises an error (e.g., `ValueError`).
    - (Optional/Ambiguous) Calling `greeting(" ")` (whitespace only) should also be considered "empty" and rejected.

## Risks and Open Questions
- Risks: If the method of rejection (e.g., raising `ValueError`) is not specified, it might break existing error handling in calling code.
- Assumptions: It is assumed that an empty string or whitespace-only string constitutes an "empty name".
- Open questions: Should we raise a specific exception type? Should strings containing only whitespace be rejected similarly to empty strings?

## Delivery Slices
1. [Smallest useful slice] Modify `greeting` to raise `ValueError` if `name` is exactly `""`.
2. [Next slice] Update validation to also reject whitespace-only strings (e.g., using `.strip()`).
