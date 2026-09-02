# Architecture Shaping: Agent Web Access Policy

## Module boundary

- Add `cli/agent_capabilities.py` for the known-capability registry, validation,
  layered exception merge, effective resolution, provenance, and stable errors.
- Keep capability resolution separate from model routing.
- Update `cli/sync.py` to retain framework and overlay policy layers, resolve
  after the final agent inventory is known, and validate before desired output
  construction reaches the write path.
- Update `cli/render.py` to translate the decision into Claude tools, the
  coupled Codex mode/tool fields, and one bounded guidance block.

## Stable invariants

- Resolution order is user override, framework override, framework default.
- Omission never removes a lower-layer denial.
- An explicit override always needs a rationale; `true` is valid only when it
  intentionally re-enables a lower denial.
- No capability catalog means legacy rendering remains unchanged.
- A present catalog makes semantic policy authoritative.
- Codex `web_search` mode and `tools.web_search` boolean form one adapter bundle
  and may not contradict each other.
- Every Claude agent under an active catalog must have a source `tools` key; an
  explicit empty list is valid, but a missing key fails with the source path
  and remediation because omission can inherit runtime tools.
