# Graph adapter implementation report

## Scope

Implemented only the Tach graph adapter and its focused tests:

- `scripts/architecture_evidence/adapters/tach.py`
- `tests/test_architecture_evidence_tach.py`

The adapter implements `collect_graph(source_root, config, raw_dir) -> (graph, tool_metadata, gaps)` against implementation interface v1. It does not modify the shared model, snapshot, CLI, policy or report code.

## Source-provenance result

The first stop boundary passed on the pinned Flow v0.28.0 checkout at `6055b6b2dd4ca5fe9a9879d61523bbd08fa0736d` using `/private/tmp/flow-architecture-tools/bin/tach` version 0.35.0:

- 45 of 45 files in the declared `cli` graph root received an inventory disposition.
- 45 module nodes and 151 internal direct-import edges were collected.
- All 151 internal edges joined to at least one exact Tach-reported source line.
- The graph retained 318 unique 1-based source references after deduplicating multiple imported symbols on the same statement.
- Zero required gaps and zero empty-provenance edges remained.
- A snapshot-layer smoke test accepted the graph and its 45-file inventory under the shared validator.

The real smoke commands were:

```text
python3 -m unittest tests/test_architecture_evidence_tach.py
python3 -m py_compile scripts/architecture_evidence/adapters/tach.py tests/test_architecture_evidence_tach.py
python3 -c '<call collect_graph against the pinned checkout and summarize counts>'
python3 -c '<call snapshot.collect with graph-only configuration and summarize validation>'
git diff --check
```

Two real collector runs into different raw directories produced equal graph values, equal deterministic tool metadata and equal empty gap lists. Their raw output directories contained `tach-map.json`, map/version stdout and stderr, and a nonraw dependency report plus stderr for every inventoried Python file. The coordinator's controlled validation run should generate the durable raw evidence; these development smoke outputs were temporary.

## Implementation behavior

The adapter copies declared source roots to a disposable directory, writes the analyzer-only `[project]` overlay below each copied source root, and generates `tach.toml` from the discovered Python-module inventory. The source checkout receives no analyzer files or Python edits.

It invokes Tach with explicit argument arrays, a fixed analysis-copy working directory, a minimal environment and a configurable positive timeout. It pins behavior to Tach 0.35.0 and rejects another reported version. Tool metadata contains deterministic version, executable/config hashes, normalized command contracts and raw-artifact names; temporary paths and timings stay out of metadata.

`tach map` is the internal edge authority. For every inventoried module, nonraw `tach report <relative-file> --dependencies` is the source-line authority. The adapter joins report targets to map endpoints, validates the reported filename and line range, aggregates repeated imports into one edge, and retains every distinct supporting statement. Missing or contradictory joins produce required string gaps that make shared collection inconclusive. It never parses Python source to infer imports.

The inventory includes every file under the graph roots after the config's declared `identity_excludes`; non-Python files receive an explicit `excluded/not-python` disposition. Containment and symlink checks apply before analysis.

## Capability boundary

Tach 0.35.0 establishes static internal direct imports for this flat-module pilot. It does not establish runtime dynamic-import completeness or classify unresolved imports. Those limitations are explicit in deterministic tool metadata:

- `static_direct_imports: available`
- `dynamic_imports: unsupported`
- `unresolved_import_classification: unsupported`
- `module_layout: flat-source-root`

The adapter does not invent unresolved records or guess dynamic edges. This limitation is visible without turning the proven static graph into a false required gap.

## Focused validation

The three adapter tests prove:

1. Map/report joining retains both exact source statements for one aggregated edge, captures raw reports and leaves the source tree byte-identical.
2. A map edge without a report source becomes a required `tach:missing-source` gap with an empty source array.
3. Relative executable paths and traversing source roots are rejected.

Focused result: 3 tests passed. Python compilation and `git diff --check` passed. Mutation check was not run in this bounded adapter slice; the missing-provenance test exercises the primary failure boundary directly, while the run-level mutation evidence belongs to the selected-function quality chunk.

## Integration notes

- Shared `snapshot.collect` currently treats every returned gap as required, so informational limitations remain in `tool_metadata.capabilities`; only collection failures and map/report inconsistencies enter `gaps`.
- Raw reports include stderr files even when empty so command diagnostics remain attributable.
- The generated `tach.toml` uses an inventory-derived module list with `depends_on = []` only to make Tach analyze the flat source root. Flow policy remains in the shared policy evaluator; the Tach config is not a boundary policy.
- The real checkout has no non-Python files in `cli`, so the current inventory is 45 processed entries and no excluded entries.

## Integrated shared-layer readiness review

Reviewed `model.py`, `snapshot.py`, `delta.py`, `policy.py` and `architecture_evidence_pilot.py` after integration, with the approved plan, interface v1 and current architecture tests as the evidence inventory. The current 22 architecture tests pass, but four contract blockers remain:

1. **Touched baseline violations can pass without reviewer disposition.** `policy.evaluate` labels an existing forbidden edge `baseline-violation` and computes `touched: true` when its source module changes, but only `forbidden-edge` and `new-cycle` affect the result. A direct oracle produced `policy_result=pass` and `overall_result=pass` for a touched forbidden baseline edge. The approved plan requires touched baseline violations to stay in a separate ledger requiring reviewer disposition. Add an explicit disposition contract, or keep this case inconclusive until a recorded disposition is validated. Add pass/inconclusive tests for untouched versus touched baseline violations.

2. **Nested canonicalization is incomplete.** `normalize_graph` sorts graph records and edge sources, but snapshot collection does not canonicalize quality records by ID, and policy loading/digesting does not canonicalize rules and exceptions by ID. Shuffling semantically unordered policy or quality records therefore changes digests and packet bytes. Canonicalize these collections before hashing, approval comparison and serialization, then add deliberately shuffled equivalence tests as required by the repeatability proof.

3. **Bad invocation does not use exit code 2.** The CLI catches configuration and path errors with evidence/runtime errors and returns 3 for all of them. For example, a missing `--config` file emits an inconclusive envelope and exits 3. The accepted command contract reserves 2 for invalid arguments and 3 for evidence or infrastructure failure. Separate invocation/config validation from collection failures and add subprocess assertions for 0, 1, 2 and 3.

4. **Report and receipt publication is not atomic.** `render` writes final report bytes directly with `xb` and then writes the final receipt. An interruption while writing can leave a truncated final report; a process interruption between files can leave an unpaired report. The accepted contract requires atomic output. Write both files in a private temporary directory, flush them, then publish with a defined two-file commit/cleanup sequence, or make a report directory the single atomically renamed output. Test injected failures before and during publication.

The reviewed integrity checks otherwise preserve the intended normal-workflow boundary: source and raw artifacts are digest-bound, graph spans are range-checked against embedded hashed sources, packet policy/approval copies are compared with embedded values, candidate bytes and report/viewer receipts are verified, and proven findings remain visible when required gaps force an inconclusive overall result. The blocked `file://` browser runtime check remains a validation limitation rather than a reason to weaken the local-only design.

## Final shared-layer recheck

The four shared-layer blockers above are resolved in the frozen implementation:

- Touched baseline violations now retain a passing policy result while forcing the overall result to `inconclusive` through an explicit reviewer-disposition gap. The focused regression test covers this separation.
- Canonical encoding now sorts rules, exceptions, quality and mutation records, source references, inventory, files and artifacts by their stable identity while preserving ordered command arguments and source lines. Reordered approved rules have the same digest and approval comparison.
- Parser errors and invalid collection configuration emit the machine-readable `invalid-invocation` envelope and return 2. Evidence, integrity and infrastructure failures remain return 3.
- Render stages complete report and receipt bytes, publishes them with exclusive hard links and treats the receipt as the completion marker. Failure to publish the receipt removes the report; an interruption between links leaves no verifiable completed pair.

No remaining material code-readiness blocker was found in the reviewed shared files. The final focused run passed 29 tests with one pinned-tool integration test skipped because `FLOW_ARCHITECTURE_PYTHON` was not set in this review process; the coordinator owns the corresponding pinned environment run. The blocked `file://` browser exercise and the four-case timed review remain explicit incomplete acceptance evidence, so the pilot itself is not yet acceptance-complete.
