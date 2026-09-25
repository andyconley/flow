# Validation Plan: local v8 verifier JSON contract

## Automated (hermetic)

- **V1:** a chartered v8 prepare with an Ollama verifier gives the verifier roster entry instructions that:
  - start with the override preamble;
  - contain no `## Output Format` heading;
  - end with `VERIFIER_CONTRACT_INSTRUCTION`.

  Its `definition_digest` equals `digest({"role", "instructions"})` over those instructions.
- **V2:** producer instructions in the same prepare are byte-identical to `_effective_specialist_for(role)`.
- **V3:** the section removal, run on the effective body of every shipped role that has `## Output Format`, removes that section and keeps the other `## ` sections. A body without the section comes back unchanged.
- **V4:** `call_local(..., structured_verifier=True)` sends a body with `format == VERIFIER_OUTPUT_SCHEMA`, and a non-verifier call sends no `format`. The request body is captured at the HTTP boundary, using the existing loopback-observer seam or an `urlopen` patch.
- **V5:** the schema agrees with the contract.
  - A candidate built to the schema that `evaluate_candidate` accepts validates in both directions.
  - A reply that satisfies the schema but breaks a contract rule is still `unusable`. Examples: a summary over `MAX_SUMMARY_BYTES`, or a `pass` with a blocking finding.
- **Full suite:** `python3.12 -m unittest discover -s tests` with `FLOW_MAF_PYTHON` set passes with 0 failures and 0 skipped, run through `suite.sh`. The exit code must not be piped away.

## Mutation checks

- **M1:** remove the section removal, so the verifier gets the raw role body. V1 must fail.
- **M2:** drop `format` from the verifier request. V4 must fail.

Restore each from a byte copy and confirm by sha256.

## Live check (against the change itself)

Through the real code path: build the verifier roster instructions with the new helper, then call `call_local(..., structured_verifier=True, timeout_seconds=60)` against local Ollama and judge each reply with `evaluate_candidate`. Run each model 3 times on each case (correct and wrong change).

- **gemma4:26b:** required 6/6 usable and correct (`valid_pass` on the correct change, `valid_fail` on the wrong one).
- **llama3.1:8b:** recorded, not required. The spike predicts 6/6.
- Record the results in `validation-results.md` and update the live-check line in `.flow/memory/STATE.md`.

## Not run

- Hosted verifiers, which aren't reachable under the current authority rules.
- A full chartered delivery end to end with a live verifier. The live check exercises the exact instruction and transport path, and the delivery plumbing is already covered hermetically.
