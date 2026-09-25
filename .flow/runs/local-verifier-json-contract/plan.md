# Plan: local v8 verifier JSON contract

- **Lane:** scout. A new run cannot enter `start-plan` without an approved definition, so this plan is recorded here and the run closes with `archive-scout`.
- **Branch:** `codex/local-verifier-json-contract`.
- **Approved by:** the engineer, 2026-09-25. Decisions: fix both the prompt and the decoding; keep the parser strict; success bar agreed; scope is any v8 verifier provider; leave thinking at the model default.
- **Compatibility:** not required. The engineer is Flow's only user.

## Problem Statement

- **What:** local models can't produce the v8 structured verifier's strict JSON verdict.
  - Flow sends the verifier's full role body (for example quality-reviewer) as the Ollama system message. That body ends with a required markdown `## Output Format`.
  - The JSON contract (`VERIFIER_CONTRACT_INSTRUCTION`) comes only at the end of the user task.
  - Models follow the system message, so every reply is judged `unusable` / `candidate_json_invalid`. Flow fails closed, and the local verifier is unusable in practice.
- **Who:** anyone running a v8 chartered delivery with an Ollama verifier. Today that is every v8 verifier (see Findings).
- **Why now:** v8 shipped in v0.35.0, and the first live check (2026-09-25, recorded in `STATE.md`) failed for both local models.

## Findings

- **Every v8 verifier is local today.** Chartered verifiers must be read-only, and read-only is allowed only with Ollama (`cli/delivery_gateway.py`, chartered roster build: `read_only != (provider == "ollama")`). The fix still goes where the roster is built, so it doesn't depend on the provider.
- **Instructions are frozen at prepare time.** Role instructions are stored in the envelope roster and bound by `definition_digest`. The verifier `input_digest` covers only the task text. New instructions change new attempts only, and no migration is needed.
- **Spike** (`spike.out` in the session scratchpad). Flow's evaluator judged each reply, 3 runs per case per model:

  | Variant | gemma4:26b | llama3.1:8b |
  |---|---|---|
  | Today | 0/4 usable | 0/4 usable |
  | Verifier system prompt | 6/6 correct | 0/6 (valid JSON inside a code fence) |
  | Prompt + Ollama `format` schema | 5/6 (1 empty) | 6/6 correct |

  The empty gemma reply came from its default thinking mode. Following the engineer's choice (a), thinking stays at the default: an empty reply is already judged unusable and uses one verifier retry.

## Desired Outcome

A v8 chartered verifier running on a capable local model returns a usable verdict (`valid_pass` or `valid_fail`) that matches the change, with no loosening of Flow's strict evaluator.

## Scope

**In scope:**

1. **Verifier instructions** (`cli/delivery_gateway.py`, chartered roster build). For each roster entry whose id is in the charter's `verifier_instance_ids`, the instructions become:
   - a fixed preamble saying Flow's verifier output contract overrides any other output format;
   - the role body with its `## Output Format` section removed, from that heading up to the next `## ` heading or the end. A role without the section is used unchanged;
   - `VERIFIER_CONTRACT_INSTRUCTION`.

   `definition_digest` is computed over these final instructions. Producer and manager instructions stay byte-identical to before. The contract also stays at the end of the task text, where the input digest proves it was asked.

   Put the composition in one small helper, for example `_verifier_instructions(role_body)` in `delivery_gateway.py` or `verifier_contracts.py`, so tests can reach it directly.
2. **Ollama `format` schema** (`cli/local_worker.py`).
   - When `structured_verifier=True`, add `"format": VERIFIER_OUTPUT_SCHEMA` to the `/api/chat` body.
   - Define `VERIFIER_OUTPUT_SCHEMA` in `cli/verifier_contracts.py`, built from the existing constants (decisions, severities, `MAX_FINDINGS`, schema version), so the contract lives in one place.
   - Non-verifier calls carry no `format`.
   - The schema only guides decoding. `evaluate_candidate` stays the sole authority, including the byte limits the schema can't express.
3. **Tests** (see `validation-plan.md`).
4. **Docs.** Add a short note to ADR 0016's verifier contract section, or the structured-verifier docs if they are the better fit. It should say the verifier system prompt excludes the role's own output format and that Ollama calls use constrained decoding.

**Out of scope:**
- enabling hosted verifiers, which the authority rules don't allow today;
- producer and manager prompts;
- fence stripping or any loosening of the parser;
- output-format changes for roles outside verifier mode;
- Ollama `think` control;
- changes to the v5–v7 protocols.

## Contracts

- **Verifier system instructions:** `PREAMBLE + strip_output_format(role_body) + VERIFIER_CONTRACT_INSTRUCTION`. The result is deterministic for a given role body.
- **Ollama request in verifier mode:** the body gains `format` (a JSON schema object). The model, messages, `num_predict` and `stream: false` are unchanged.
- **Evaluation:** unchanged. The same dispositions and reason codes apply.

## Risks

- **The section-removal regex is tied to role markdown layout.** Mitigations: a test runs it on the real effective body of every role Flow ships, and asserts that `## Output Format` is absent from the result and that the other sections survive.
- **Thinking models may still return an empty reply sometimes.** This fails closed as `unusable` and is covered by the retry budget. It is accepted.
- **Older Ollama versions may reject a schema-valued `format`.** The installed version is 0.32.1, where it works. A rejected request would show up as a transport failure, not a false verdict.
