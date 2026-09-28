# Validation Plan

- Focused test reproduces the noncanonical intent previously sealed by `approve-definition`.
- Compare `run.json` and `events.jsonl` bytes before and after rejected approval.
- Confirm valid canonical intent still reaches `definition_approved` and records expected digests.
- Run `/opt/homebrew/bin/python3.12 -m unittest discover -s tests -p test_flow.py`.
- Require independent read-only verifier approval.
