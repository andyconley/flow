# flow-implement

Use for gated implementation work when the task is large enough to benefit from explicit phases and durable artifacts.

Prefer this command when:

- work spans multiple files or sessions
- architecture or UX contract decisions matter
- reviewability and traceability are important

Phases:

1. requirements
2. as-is
3. plan
4. implementation
5. review
6. validation
7. handback

Artifacts live under `.flow/runs/<work-id>/`.

Expected outputs:

- durable run artifacts
- code and test changes
- review findings or sign-off
- validation evidence
- structured handback for archive or acceptance review
