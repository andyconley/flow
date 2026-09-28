# local-verifier output: attempt 1

Ollama `gemma4:26b`. One call was Flow-granted, sent, and observed as `flow_observed_local_http_response`, in 7.04 s against the 60 s cap.

- **Evaluation:** `valid_pass` / `accepted_pass` (action `6966b734…`, evaluation digest `5dcd3b36…`).
- **Summary from the model:** the raw `|` is kept in `flow.toml`, both generated tables use `\|`, `cli-reference.md` covers all five refusals and points to `recover-delivery-lead`, the scope is limited to the four files, and no extra flags were added.
- **Findings:** none.
- **Preflight gate** (`evidence/verifier-gate.json`): `go` in 4.95 s on run 2's real four-file diff.
