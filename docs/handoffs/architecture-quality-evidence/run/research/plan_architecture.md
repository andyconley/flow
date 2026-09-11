# Architecture planning review

## Evidence status

- **Observed:** `planning-proposal.md`, `validation-plan.draft.md`, and `implementation-handoff.draft.md` preserve the approved solution: all four chunks, the clean isolated `v0.28.0` checkout, a pilot-only script, one self-contained local browser report, and no production CLI/lifecycle/gate change.
- **Observed:** the repository documents `cli/` as dependency-free production runtime code and `scripts/` as maintainer tooling. A pilot entrypoint under `scripts/` fits that boundary; registering it in `cli/flow.py` would widen install/runtime scope without helping the pilot.
- **Observed:** Tach 0.35.0 maps the flat CLI, but `check`/`report` require an analysis-only package overlay because `cli/setup.py` is mistaken for packaging metadata. The overlay must remain outside source identity and never rewrite the `.py` files.
- **Unverified:** complete Tach edge-to-line joins, mutmut provenance, the final Cytoscape.js asset/version/hash, offline `file://` behavior, and the reviewer exercise remain implementation proof.

## Recommended file ownership

Retain the proposal's names and add only the seams needed to keep policy separate from graph comparison:

```text
scripts/architecture_evidence_pilot.py
scripts/architecture_evidence/__init__.py
scripts/architecture_evidence/model.py
scripts/architecture_evidence/snapshot.py
scripts/architecture_evidence/delta.py
scripts/architecture_evidence/policy.py
scripts/architecture_evidence/report.py
scripts/architecture_evidence/adapters/__init__.py
scripts/architecture_evidence/adapters/tach.py
scripts/architecture_evidence/adapters/radon.py
scripts/architecture_evidence/adapters/coverage_json.py
scripts/architecture_evidence/adapters/mutmut.py
scripts/architecture_evidence/schema/evidence-packet-v1.schema.json
scripts/architecture_evidence/assets/cytoscape.min.js
scripts/architecture_evidence/assets/manifest.json
scripts/architecture_evidence/assets/CYTOSCAPE_LICENSE.txt
scripts/architecture_evidence/requirements.lock
tests/test_architecture_evidence.py
tests/fixtures/architecture_evidence/
docs/architecture-evidence-pilot.md
```

`model.py` owns validation, canonical JSON and digests. `snapshot.py` owns source identity, inventory and contained source excerpts. `delta.py` owns baseline/candidate graph comparison and cycle classification. `policy.py` consumes a validated delta; it does not infer analyzer semantics. `report.py` is a pure packet-to-bytes renderer and cannot run tools or recompute the verdict. Each adapter owns invocation and normalization of one external tool; shared code imports no parser/tool library.

Place the analyzer-only `cli/pyproject.toml` and Tach configuration as a mirrored fixture below `tests/fixtures/architecture_evidence/tach-overlay/`. `collect` copies that overlay into a disposable analysis copy, records its digest separately, and verifies that analyzed Python hashes still equal the requested source snapshot. Do not add the workaround beside production `cli/setup.py` in the checked-in source tree.

Pin the pilot Python dependencies with hashes in `requirements.lock`. Pin the vendored Cytoscape.js distribution and license in `assets/manifest.json`; `report.py` verifies the asset digest before embedding it. Do not add `package.json`, a Node build, or a runtime dependency installer.

## Command contract adjustments

The proposed `collect`, `compare`, and `render` commands are coherent. Add an explicit review-time integrity command:

```text
python scripts/architecture_evidence_pilot.py verify --packet PACKET_DIR --candidate ROOT --report REPORT.html
```

`verify` rechecks packet/raw/report digests, candidate content identity, policy and overlay identity, then emits the same operation/result envelope. A valid rendered packet whose policy result is `fail` remains a successful render artifact with a failing pilot result; keep those statuses separate. Exit `1` remains a proven policy failure, `2` invalid invocation, and `3` inconclusive evidence/infrastructure. No command silently overwrites an existing evidence path.

External commands use explicit executable paths and argument arrays with `shell=False`, a fixed working directory, timeout, minimal inherited environment, and captured output. Tool/config/source/test identities key caches; disable cache for first mutation proof. Retain raw bytes, digest, version, arguments, exit code and bounded diagnostics. Never read analyzer configuration from HOME or invoke package installation/fetching during evidence generation.

## Local browser packaging and source safety

`render` should emit exactly one deterministic `architecture-report.html`. Cytoscape.js, application JavaScript, CSS, packet data and bounded source excerpts are inlined at generation; viewing performs no `fetch`, opens no server and makes no network request. The report must still work after it is moved away from both checkout and packet directory.

Embed packet JSON as inert data, escaping `<`, `>`, `&`, U+2028 and U+2029 so a `</script>` source string cannot close its container. Render labels, paths and excerpts with `textContent`, never `innerHTML` or evaluated templates. Add a restrictive meta CSP with no connections, frames, forms, objects or base URL; allow only the exact inlined script/style hashes or deterministic nonce. Test the output for external `src`, `href` and connection targets.

Source drilldown should use embedded evidence by default: repository-relative path, 1-based inclusive span, file digest, exact matched import lines and a small fixed context window. Resolve paths before reading; reject `..`, absolute-path injection and symlinks escaping the declared source root. Cap per-excerpt line/byte counts and total report size. Omit HOME paths, credentials, environment dumps, analyzer cache paths and raw command output. A selectable `path:line` is enough for portable review; optional absolute `file://` links must be local-only and absent by default.

## UI states and accessibility

The proposal names the main interactions. Make these states directly testable:

- verified `pass`, policy `fail`, and evidence `inconclusive`;
- graph with changes, valid graph with no changes, and filter with no matches;
- added/removed edge, new cycle, baselined cycle, touched baseline violation and prohibited edge;
- unresolved/dynamic import, excluded/failed file, missing source span and unsupported quality capability;
- selected node/edge/function, unavailable excerpt, corrupt/unsupported packet and candidate mismatch.

Color can reinforce status but cannot encode it alone; use text plus line/shape style and a visible legend. Provide keyboard-operable mode/filter/status controls, pan/zoom/reset, visible focus, reduced motion, result-count announcements, and detail-panel focus return. There are no approve, mutate or analyzer actions in the report.

Cytoscape's canvas is not an accessible source of truth. Include a synchronized semantic table/list of components, edges, cycles, policy findings, gaps and quality evidence. The table supports the same filtering and detail pane, has real headings, and is reachable by a skip link. A reviewer must be able to complete the inspection without pointer gestures or interpreting the graph image.

## Meaningful tests and corrections

Prioritize behavior tests over assertions that mirror JSON field construction:

1. Repeat collection with permuted analyzer records and different output paths; canonical graph bytes/digest stay equal while timing manifests differ.
2. Run Tach against the real isolated flat CLI fixture without changing Python bytes; assert selected collector/watermark/store edges and exact contained source spans. Any unclassified in-scope file or unmapped resolved edge is `inconclusive`.
3. Exercise clean, added/removed edge, forbidden edge, new cycle, baselined cycle, added cyclic edge inside an existing component, touched baseline violation and unmapped rename cases against independent oracles.
4. Change candidate bytes, source excerpt, policy, overlay, raw artifact, adapter version and viewer asset one at a time; every mismatch is detected and never yields `pass`.
5. Pass Python and hand-authored TypeScript-shaped snapshots through the same validator, evaluator and renderer. The fixture proves contract portability only.
6. Render hostile labels/excerpts containing markup, closing-script strings, bidirectional controls, control characters and long lines; they display as bounded text and cannot create network or executable content.
7. Keep the real selected-function and mutation proofs from `validation-plan.draft.md`; verify the executed module path is inside the disposable mutant workspace before interpreting results.

Because `tests/` is not a Python package, use discovery for the targeted test rather than `python -m unittest tests.test_architecture_evidence`:

```bash
/opt/homebrew/bin/python3.12 -m unittest discover -s tests -p 'test_architecture_evidence.py'
/opt/homebrew/bin/python3.12 -m unittest discover -s tests
git diff --check
```

Record a real-browser checklist for the moved offline `file://` report: pan/zoom/reset; filter and baseline/candidate/delta modes; every edge state; source drilldown; keyboard-only table path; focus return; reduced motion; empty, invalid and inconclusive states; and network-request observation. Screenshots support this record but do not replace it.

## Planning disposition

- **Recommended:** incorporate the file split, `verify` command, single-file safety contract, accessible table, and corrected targeted test command into the final plan/handoff.
- **Recommended:** make complete Tach source provenance the Chunk 1 stop boundary. If the disposable overlay cannot produce exact joins without modifying source, return `inconclusive` and select another existing analyzer; do not write a Python import parser.
- **Recommended:** link the packet, HTML report, approved policy, raw-artifact manifest and completed browser checklist from the existing `review.md`. Keep production install, CLI registration, lifecycle and gates untouched.
- **Unverified:** final plan readiness still depends on naming the canonical approved-policy path, artifact output root, selected mutation test nodes, pinned tool hashes and the exact proven Tach overlay/report invocation.
