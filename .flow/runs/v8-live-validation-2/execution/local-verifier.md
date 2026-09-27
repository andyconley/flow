# local-verifier output: not reached

Neither attempt reached a verifier proposal, and no verifier call was granted or sent.

- **Attempt 1** (`22ab86c3…`) aborted on the malformed manager progress reply that would have selected the verifier (D4).
- **Attempt 2** (`0fa56024…`) failed at the edit check after an inspect-only producer turn.

The preflight verifier gate (`evidence/verifier-gate-3.json`: a valid verdict in 3.1 s) is the only evidence from the local verifier. See `validation-results.md`.
