# Medium-confidence expertise expansion results

The fixtures in each role directory were written before these runs. Each arm
uses the same Claude client, model, effort, prompt, maximum turns, and budget;
the treatment appends the generated candidate body and the control appends the
unchanged role body. Raw client JSON is retained in each role's `runs/`
directory.

## Disposition

| Role | Primary | Counter-case | Gate | Evidence-based disposition |
| --- | --- | --- | --- | --- |
| architect | pass | pass | pass | The treatment makes the compatibility decision, names the adapter's expiry and reversal conditions, and avoids an ADR for the local refactor. |
| test-engineer | pass | pass | pass | The treatment supplies behavior-level oracles for import paths and retains a unit-level posture for the formatter. |
| product-manager | tie | pass | fail | Both arms make the same evidence-backed release choice; the treatment adds detail but does not show a named role-owned improvement. |
| quality-reviewer | tie | pass | fail | Both primary arms reject the missing malformed-input evidence for the same criterion. The treatment's clean counter verdict is correct, but it cannot turn the primary tie into a pass. |
| lead-developer | pass | fail | fail | The treatment gives a reversible migration plan, but on the one-file counter-case it requests missing specifics and supplies a template instead of a direct, proportionate plan. |

## Implication

This release envelope does not meet its all-five role gate. Do not merge or
claim that the new expertise improves every target role. Repair must preserve
these fixtures, explain the corpus or role-body change, and rerun both arms for
each failed role. The architect and test-engineer evidence remains valid but
does not waive the failed gates.

## Runtime note

Native `claude -p --agent lead-developer` stalled without producing output. The
lead-developer comparison therefore uses the generated candidate body at
`~/.claude/agents/lead-developer.md` and the unchanged source body through the
same `--append-system-prompt-file` path. This isolates composition while
avoiding the client invocation failure; both arms use Sonnet at medium effort.

## Approved discriminating rerun

The 2026-09-09 amendment added a second primary case for product-manager and
quality-reviewer. Both arms were rerun through the same append-system-prompt
path at the configured model and medium effort. The raw files are named
`*-primary-discriminating.json` in their existing role directories.

| Role | Result | Disposition |
| --- | --- | --- |
| product-manager | Both arms prioritize removing the documented workaround, reject sponsor count as a priority proxy, and define the same smallest slice. | Tie; still fails the primary improvement gate. |
| quality-reviewer | Both arms reject the generic `400` as insufficient evidence and require row/field assertions. | Tie; still fails the primary improvement gate. |

The amendment confirms that the current source-backed entries do not create a
measurable role-owned difference beyond the unchanged role bodies. It does not
replace the original frozen cases or make the release eligible for merge.

## Role-method differentiation outcome

A later comparison established a passing lead-developer short/full-plan method,
so the original lead-developer failure is superseded by that preserved pass.
The separately frozen `repair-2` attempt then replaced only the failed product
and quality methods. Its product-manager treatment missed one required ratio
and its control performed two distinctive items; its quality-reviewer treatment
filed Critical before the required reasoning chain and its control performed
two distinctive items. Both counters passed safely, but both strict role gates
remain false.

The combined disposition is therefore: architect pass, test-engineer pass,
lead-developer pass, product-manager fail, quality-reviewer fail. The all-five
release remains ineligible for merge. Detailed immutable results are in
`../role-method-differentiation/repair-2/results.json`.
