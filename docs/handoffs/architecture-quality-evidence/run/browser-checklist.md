# Pending manual browser validation

Status: NOT RUN. The browser automation security policy rejected the local file URL and explicitly prohibited a workaround. Andy must open the saved report manually in a local browser to complete this evidence.

Use the evidence-assisted report at the appropriate point in `evidence/review-exercise/README.md`; do not preview all cases before the timed exercise.

- [ ] Record browser/version, report SHA256, date and reviewer.
- [ ] Open offline, then move/copy the standalone report away from the source checkout and reopen.
- [ ] Inspect baseline, candidate and delta; search, component filters, reset, zoom/pan, node and edge details, and exact source excerpts.
- [ ] Check filtered-empty, partial/inconclusive and truncated-source presentation; exercise invalid/empty fixtures separately.
- [ ] Complete keyboard-only navigation through controls and node/edge list; inspect focus return, Escape and non-color status cues.
- [ ] Confirm no external network requests during load or interaction.
- [ ] Render a hostile-label/source fixture and confirm it displays literally without execution.

Record observed outcomes and failures in validation-results.md. Generator unit tests are not substitutes for these runtime checks.
