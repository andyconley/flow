# Session Model Advice

Use this policy at the legal advice point named by each entry command. Advice is
for the parent session. Delegated-agent routing remains a separate effective
configuration.

## Fact collection

Run:

```bash
flow model context --runtime <claude|codex> --lane <boot|define|solution|plan|resume> --json
```

Use the active runtime only. The result reports declared profile mappings,
mapping provenance, active-parent evidence, bounded history, global capacity
when available, and limitations. Missing, stale, partial, unreadable, or
incompatible history is unknown evidence rather than zero use. Usage and
capacity do not establish quality or latency. Only verified same-session host
evidence may be called observed; a user statement is declared; otherwise the
current parent is unknown.

## Judgment

Assess the next meaningful body of work, with whole-run consequences as
context:

- `mechanical`: explicit transformations or administration with easy checks.
- `working`: bounded, familiar implementation with ordinary coordination.
- `judgment`: architectural ambiguity, consequential tradeoffs, or acceptance
  decisions that need stronger judgment.
- `demanding`: unusually difficult unresolved reasoning with broad
  consequences or weak recovery.

Choose quality and confidence first, then speed. Cost and capacity may inform
the explanation but cannot lower the required posture by themselves. Unknown
scope produces provisional advice. A routine next step may use a smaller
profile inside a difficult run when its consequences and switching overhead
support that choice.

After choosing the semantic profile, run:

```bash
flow model resolve --runtime <claude|codex> --profile <profile> --json
```

Do not invent a model or effort when resolution is unresolved, disabled, or
invalid. A resolved mapping still has unverified account availability until
live evidence establishes it.

## Response

State the semantic profile, native model and effort when resolved, a brief
reason, and whether advice is supported or provisional. Label active-parent
identity separately as observed, declared, or unknown. Use `keep_current`
only when reliable current identity matches a suitable recommendation;
otherwise use `change_recommended` or `provisional`. Say that no switch was
performed.

Advice adds no approval question or lifecycle gate. Continue the lane on the
current model. Do not repeat unchanged advice because a command changed.
Reassess when task scope, cross-component consequences, failures, verification
needs, current model, or configuration changes materially.
