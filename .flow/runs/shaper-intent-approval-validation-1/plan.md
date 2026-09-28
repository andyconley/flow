# Plan

1. Locate `approve-definition` validation and persistence ordering in `cli/runstate.py`.
2. Call the existing canonical Shaper-intent validator before constructing or writing the transition result.
3. Add focused tests for invalid-intent atomic rejection and valid-intent compatibility.
4. Update only directly affected guidance, run `test_flow.py`, and produce independent verifier evidence.
