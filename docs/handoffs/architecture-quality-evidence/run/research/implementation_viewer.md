## Viewer implementation report

### Delivered

- `scripts/architecture_evidence/report.py` exposes `render_html(packet: dict) -> bytes` and imports only Python standard-library modules.
- The renderer produces one self-contained local-file HTML report with packet data, Cytoscape, CSS, and interaction JavaScript embedded in the output. It verifies the vendored asset hash before rendering.
- The report provides baseline, candidate, and delta modes; component and text filters; reset; keyboard zoom/pan; graph selection; a synchronized keyboard-accessible node/edge list; source/quality details; and a visible findings, gaps, cycle-ledger, inventory, and capability-limitation section.
- Delta mode unions candidate and baseline nodes. Removed nodes are retained, marked as removed, and source/quality details resolve from the baseline snapshot.
- UI result language keeps render, policy, and overall evidence outcomes separate. A graph-only packet explicitly says required quality is disabled and is not a full-pilot pass. It includes loading, empty, filtered-empty, graph-library fallback, and inconclusive states.
- Packet JSON escapes closing-script characters. Before embedding, the renderer projects packets to UI-needed source identity, graph/sources, quality, capabilities, results, and approval digests; full approval text/events, configs, and raw artifact paths remain in packet files. Labels and excerpts use `textContent`; the document has a restrictive CSP, no network sources, no forms/frames/objects/base URL, and report/excerpt size limits. A line or byte limited source excerpt visibly states that drilldown is incomplete.

### Assets and safety evidence

- Vendored Cytoscape.js 3.33.1: `assets/cytoscape.min.js`, SHA-256 `f55947f3daa3bae53209d4b885c195c157f595c225e508a6b382598d9452d6e2`.
- The asset license and hash-bearing `assets/manifest.json` are included beside the asset.
- Focus indicators, a skip link, visible text status, reduced-motion behavior, and semantic buttons/list provide non-pointer access. Color is accompanied by state words in the list and status text.

### Focused checks

- `python3 -m unittest tests/test_architecture_report.py` validates self-contained/offline markup, CSP and keyboard-list presence, hostile closing-script input escaping, asset hash integrity, type rejection, removed-node/truncation behavior, quality path matching, semantic finding/limitation sections, endpoint-preserving filtering, keyboard graph controls, and packet privacy projection.

### Limits

- Browser execution and root model/CLI integration remain with the coordinator. The renderer accepts the agreed packet dictionary and does not import or redefine the shared model.

### Read-only integration review

The earlier approval, packet-file binding, viewer-digest, and node-excerpt observations have been addressed in the current shared code: approval plan/event text is checked against copied files; embedded policy/approval must equal packet artifacts; the receipt binds the viewer distribution; and graph nodes require source excerpts. The viewer preserves these fields in packet files but does not expose their raw values in HTML.

Focused viewer checks are source/unit tests only. Browser `file://` behavior and the human review exercise remain pending validation.
