"""Offline, inert HTML rendering for architecture-evidence packets.

The renderer deliberately accepts dictionaries rather than the pilot model.  The
shared model validates packets before this presentation layer is called, while
this module still treats every packet value as untrusted display data.
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any


_ASSETS = Path(__file__).with_name("assets")
_CYTOSCAPE = _ASSETS / "cytoscape.min.js"
_MAX_EXCERPT_LINES = 200
_MAX_EXCERPT_BYTES = 64 * 1024
_MAX_REPORT_BYTES = 10 * 1024 * 1024


def _json_for_script(value: Any) -> str:
    """Encode inert JSON so a value cannot terminate its script element."""
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _csp_hash(text: str) -> str:
    digest = base64.b64encode(hashlib.sha256(text.encode("utf-8")).digest()).decode(
        "ascii"
    )
    return "sha256-" + digest


def _read_asset() -> str:
    data = _CYTOSCAPE.read_bytes()
    manifest = json.loads((_ASSETS / "manifest.json").read_text(encoding="utf-8"))
    expected = manifest["cytoscape"]["sha256"]
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise RuntimeError("Cytoscape asset hash does not match assets/manifest.json")
    return data.decode("utf-8")


def _viewer_snapshot(snapshot: dict) -> dict:
    """Keep only data required by the local viewer; packets remain the audit record."""
    source = snapshot.get("source", {})
    sources = {
        path: {"sha256": item.get("sha256"), "lines": item.get("lines", [])}
        for path, item in snapshot.get("sources", {}).items()
    }
    return {
        "source": {"digest": source.get("digest"), "revision": source.get("revision")},
        "graph": snapshot.get("graph", {}),
        "sources": sources,
        "quality": snapshot.get("quality", {}),
        "tools": {"capabilities": snapshot.get("tools", {}).get("capabilities", {})},
        "config": {
            "quality": {
                "required": snapshot.get("config", {})
                .get("quality", {})
                .get("required")
            }
        },
    }


def _viewer_packet(packet: dict) -> dict:
    """Project a packet for display without exposing approval/config/raw artifacts."""
    approval = packet.get("approval", {})
    return {
        "schema_version": packet.get("schema_version"),
        "kind": packet.get("kind"),
        "baseline": _viewer_snapshot(packet.get("baseline", {})),
        "candidate": _viewer_snapshot(packet.get("candidate", {})),
        "delta": packet.get("delta", {}),
        "policy_result": packet.get("policy_result"),
        "overall_result": packet.get("overall_result"),
        "findings": packet.get("findings", []),
        "gaps": packet.get("gaps", []),
        "approval": {
            key: approval.get(key)
            for key in ("policy_digest", "plan_digest", "approver")
        },
    }


_CSS = r"""
:root{color-scheme:light dark;font-family:ui-sans-serif,system-ui,sans-serif;color:#152033;background:#f6f8fb}
*{box-sizing:border-box}body{margin:0;line-height:1.45}a{color:inherit}button,input,select{font:inherit}
.skip{position:absolute;left:-999px;top:0;background:#111;color:#fff;padding:.5rem;z-index:10}.skip:focus{left:.5rem;top:.5rem}
header{padding:1.25rem max(1rem,calc((100% - 76rem)/2));background:#fff;border-bottom:1px solid #d6dbe3}h1{margin:0;font-size:1.5rem}h2{font-size:1.1rem;margin:.2rem 0}.lede{margin:.3rem 0 0;color:#4b5563}
.status{margin:1rem auto;max-width:76rem;padding:.75rem 1rem;border-left:5px solid #3569a8;background:#e8f0fb}.status[data-state="fail"],.status[data-state="error"]{border-color:#ad2436;background:#fbeaec}.status[data-state="inconclusive"]{border-color:#9a6500;background:#fff5d7}.status[data-state="pass"]{border-color:#1c7c54;background:#e6f5ed}
main{max-width:76rem;margin:auto;padding:0 1rem 2rem}.identity{display:grid;grid-template-columns:repeat(auto-fit,minmax(16rem,1fr));gap:.75rem;margin:1rem 0}.card{padding:.75rem;background:#fff;border:1px solid #d6dbe3;border-radius:.35rem;overflow-wrap:anywhere}.label{display:block;font-size:.82rem;font-weight:700;color:#4b5563;text-transform:uppercase;letter-spacing:.04em}
.controls{display:flex;gap:.75rem;flex-wrap:wrap;align-items:end;margin:1rem 0}.control{display:grid;gap:.2rem}.modes{display:flex;gap:.35rem}.modes button[aria-pressed="true"]{background:#193d6b;color:#fff}.controls button,.controls input,.controls select{min-height:2.35rem;border:1px solid #a7b0bd;border-radius:.25rem;padding:.35rem .55rem;background:#fff;color:#172033}.controls button:focus-visible,.controls input:focus-visible,.controls select:focus-visible,.item:focus-visible{outline:3px solid #f0a000;outline-offset:2px}
.workspace{display:grid;grid-template-columns:minmax(0,2fr) minmax(18rem,1fr);gap:1rem}.graph,.details,.list-wrap{background:#fff;border:1px solid #d6dbe3;border-radius:.35rem}.graph{height:32rem;position:relative}.graph canvas{outline:none}.details{padding:1rem;min-height:14rem}.details pre{white-space:pre-wrap;word-break:break-word;background:#f2f4f7;padding:.7rem;max-height:22rem;overflow:auto}.list-wrap{margin-top:1rem;padding:1rem}.items{list-style:none;padding:0;margin:0;display:grid;gap:.35rem}.item{width:100%;text-align:left;padding:.55rem;border:1px solid #c8d0db;border-radius:.25rem;background:#fff;cursor:pointer}.item .kind{font-size:.8rem;font-weight:700;margin-right:.35rem}.item[data-change="added"]{border-left:5px solid #1c7c54}.item[data-change="removed"]{border-left:5px solid #9b293d}.item[data-change="unchanged"]{border-left:5px solid #5d6b7b}.empty{padding:1rem;color:#4b5563}.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
@media(max-width:800px){.workspace{grid-template-columns:1fr}.graph{height:24rem}}@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;transition:none!important;animation:none!important}}
"""


_APP_JS = r"""
(() => {
  "use strict";
  const packet = JSON.parse(document.getElementById("packet-data").textContent);
  const $ = (id) => document.getElementById(id);
  const state = {mode:"delta", component:"", search:"", cy:null, selected:null};
  const status = (packet.overall_result || "inconclusive").toLowerCase();
  const baseline = packet.baseline || {}, candidate = packet.candidate || {};
  const graph = (snap) => (snap && snap.graph) || {nodes:[],edges:[]};
  const delta = packet.delta || {};
  const edgeIds = new Map();
  ["added_edges","removed_edges","unchanged_edges"].forEach((key) => (delta[key] || []).forEach((edge) => edgeIds.set(edge.id, key.replace("_edges", ""))));
  function text(node, value) { node.textContent = value == null ? "" : String(value); }
  function title(value) { const v = document.createElement("span"); text(v, value); return v; }
  function sourceFor(path, requested, change) {
    const snapshot = change === "removed" ? baseline : candidate;
    const source = ((snapshot.sources || {})[path] || {});
    const lines = Array.isArray(source.lines) ? source.lines : [];
    const start = Math.max(0, ((requested && requested.start_line) || 1) - 6);
    const requestedEnd = ((requested && requested.end_line) || lines.length) + 5;
    const end = Math.min(lines.length, requestedEnd, start + 200);
    const excerpt = lines.slice(start, end).map((line, i) => `${String(start + i + 1).padStart(5)} | ${line}`).join("\n");
    if (new TextEncoder().encode(excerpt).length > 65536) return {text:"Source excerpt unavailable: it exceeds the report safety limit.", limited:true};
    if (!excerpt) return {text:"Source excerpt unavailable in this packet.", limited:true};
    return {text:excerpt, limited:end < lines.length && end < requestedEnd};
  }
  function nodesForMode() {
    if (state.mode === "baseline") return (graph(baseline).nodes || []).map((node) => ({...node,_change:"unchanged"}));
    if (state.mode === "candidate") return (graph(candidate).nodes || []).map((node) => ({...node,_change:"unchanged"}));
    const previous = new Map((graph(baseline).nodes || []).map((node) => [node.id, node]));
    const current = new Map((graph(candidate).nodes || []).map((node) => [node.id, node]));
    const nodes = [...current.values()].map((node) => ({...node,_change:previous.has(node.id) ? "unchanged" : "added"}));
    previous.forEach((node, id) => { if (!current.has(id)) nodes.push({...node,_change:"removed"}); });
    return nodes;
  }
  function edgesForMode() { return state.mode === "baseline" ? graph(baseline).edges || [] : state.mode === "candidate" ? graph(candidate).edges || [] : [...(delta.added_edges || []), ...(delta.removed_edges || []), ...(delta.unchanged_edges || [])]; }
  function textMatches(record) { return JSON.stringify(record).toLowerCase().includes(state.search); }
  function visibleEvidence() {
    const allNodes = nodesForMode(); const byId = new Map(allNodes.map((node) => [node.id, node]));
    const selectedNodes = allNodes.filter((node) => (!state.component || node.parent === state.component) && textMatches(node));
    const selectedEdges = edgesForMode().filter((edge) => {
      const from = byId.get(edge.from), to = byId.get(edge.to);
      const componentMatch = !state.component || (from && from.parent === state.component) || (to && to.parent === state.component);
      return componentMatch && (textMatches(edge) || (from && textMatches(from)) || (to && textMatches(to)));
    });
    const ids = new Set(selectedNodes.map((node) => node.id));
    selectedEdges.forEach((edge) => { ids.add(edge.from); ids.add(edge.to); });
    return {nodes:allNodes.filter((node) => ids.has(node.id)), edges:selectedEdges};
  }
  function summarize() {
    const graphOnly = [baseline,candidate].some((snap) => ((snap.config || {}).quality || {}).required === false);
    const message = graphOnly && status === "pass" ? "Architecture and policy evidence passed for this graph-only packet. Required quality evidence is disabled; this is not a full-pilot pass." : status === "pass" ? "The packet is valid evidence; reviewer judgment remains separate." : status === "fail" ? "A proven policy finding is present." : "Required evidence is missing, stale, or incomplete.";
    text($("overall"), `Evidence result: ${status}. ${message}`);
    $("overall").dataset.state = status;
    text($("baseline-id"), (baseline.source || {}).digest || "Unavailable");
    text($("candidate-id"), (candidate.source || {}).digest || "Unavailable");
    text($("policy-result"), `Policy: ${packet.policy_result || "unavailable"}`);
  }
  function details(record, type, change) {
    state.selected = record && record.id;
    const panel = $("details"); panel.replaceChildren();
    const h = document.createElement("h2"); text(h, record ? `${type}: ${record.label || record.id || "unnamed"}` : "Details"); panel.append(h);
    if (!record) { const p = document.createElement("p"); text(p, "Choose a node or dependency to inspect its evidence."); panel.append(p); return; }
    const summary = document.createElement("p"); text(summary, type === "edge" ? `${record.from} → ${record.to} (${record.kind || "dependency"})` : `${record.path || "No source path"} · ${record.language || "unknown language"}`); panel.append(summary);
    const refs = type === "edge" ? record.sources || [] : [{path:record.path, start_line:record.start_line, end_line:record.end_line}];
    refs.forEach((ref) => { const h3 = document.createElement("h3"); text(h3, `${ref.path || "Source"} (${ref.start_line || "?"}–${ref.end_line || "?"})`); const excerpt = sourceFor(ref.path, ref, change); const pre = document.createElement("pre"); text(pre, excerpt.text); panel.append(h3, pre); if (excerpt.limited) { const warning = document.createElement("p"); warning.className="status"; warning.dataset.state="inconclusive"; text(warning, "Source drilldown is incomplete; do not treat this excerpt as complete evidence."); panel.append(warning); } });
    if (type === "node") { const quality = ((change === "removed" ? baseline : candidate).quality || {}).records || []; const records = quality.filter((item) => item.path === record.path || item.symbol === record.id || item.id === record.id); if (records.length) { const h3 = document.createElement("h3"); text(h3, "Quality evidence"); panel.append(h3); records.forEach((item) => { const pre = document.createElement("pre"); text(pre, JSON.stringify(item, null, 2)); panel.append(pre); }); } }
    if (state.returnFocus) panel.focus();
  }
  function appendNote(list, textValue) { const li = document.createElement("li"); text(li, textValue); list.append(li); }
  function evidenceNotes() {
    const list = $("notes"); list.replaceChildren();
    appendNote(list, "Graph scope: static internal direct imports only. Dynamic imports and runtime calls are not established by this report.");
    [baseline,candidate].forEach((snap, index) => { const capabilities = ((snap.tools || {}).capabilities || {}); Object.keys(capabilities).sort().forEach((key) => { if (capabilities[key] !== "available") appendNote(list, `${index ? "Candidate" : "Baseline"} capability ${key}: ${capabilities[key]}.`); }); });
    const inventory = graph(candidate).inventory || []; const counts = inventory.reduce((all, item) => { all[item.status] = (all[item.status] || 0) + 1; return all; }, {});
    appendNote(list, `Candidate inventory: ${counts.processed || 0} processed, ${counts.excluded || 0} excluded, ${counts.failed || 0} failed.`);
    (packet.findings || []).forEach((finding) => appendNote(list, `Finding (${finding.kind || "unclassified"}): ${finding.message || finding.id}.`));
    (packet.gaps || []).forEach((gap) => appendNote(list, `Evidence gap: ${typeof gap === "string" ? gap : JSON.stringify(gap)}.`));
    (delta.baseline_cycles || []).forEach((cycle) => appendNote(list, `Baseline cycle ledger: ${(cycle.members || []).join(", ") || "members unavailable"}.`));
    (delta.new_cycles || []).forEach((cycle) => appendNote(list, `New cycle: ${(cycle.members || []).join(", ") || "members unavailable"}.`));
    if (!list.children.length) appendNote(list, "No findings, evidence gaps, or cycle entries were supplied.");
  }
  function items() {
    const list = $("items"); list.replaceChildren();
    const {nodes, edges} = visibleEvidence();
    if (!nodes.length && !edges.length) { const empty = document.createElement("p"); empty.className="empty"; text(empty, state.search || state.component ? "No graph evidence matches the current filter." : "This packet contains no graph evidence."); list.append(empty); return; }
    nodes.forEach((node) => makeItem(node, "node", node._change)); edges.forEach((edge) => makeItem(edge, "edge", edgeIds.get(edge.id) || "unchanged"));
  }
  function makeItem(record, type, change) { const li = document.createElement("li"); const button = document.createElement("button"); button.type="button"; button.className="item"; button.dataset.change = change; const kind = document.createElement("span"); kind.className="kind"; text(kind, type === "node" ? "Module" : `${change || "dependency"} dependency`); const name = document.createElement("span"); text(name, type === "node" ? (record.label || record.id) : `${record.from} → ${record.to}`); button.append(kind, name); button.addEventListener("click", () => { state.returnFocus = button; details(record, type, change); if (state.cy) { const ele = state.cy.$id(record.id); if (ele.length) { state.cy.elements().unselect(); ele.select(); state.cy.center(ele); } } }); li.append(button); $("items").append(li); }
  function draw() {
    if (state.cy) state.cy.destroy();
    const evidence = visibleEvidence();
    const nodes = evidence.nodes.map((node) => ({data:{id:node.id,label:node.label || node.id,change:node._change}}));
    const edges = evidence.edges.filter((edge) => nodes.some((node) => node.data.id === edge.from) && nodes.some((node) => node.data.id === edge.to)).map((edge) => ({data:{id:edge.id,source:edge.from,target:edge.to,change:edgeIds.get(edge.id) || "unchanged"}}));
    if (!window.cytoscape) { text($("graph"), "Graph library unavailable. Use the semantic evidence list below."); return; }
    state.cy = window.cytoscape({container:$("graph"),elements:{nodes,edges},layout:{name:"cose",animate:false,padding:32},style:[{selector:"node",style:{"label":"data(label)","font-size":"11px","text-wrap":"wrap","text-max-width":"120px","background-color":"#3569a8","color":"#172033","text-outline-color":"#fff","text-outline-width":2}},{selector:"node[change = 'added']",style:{"background-color":"#1c7c54"}},{selector:"node[change = 'removed']",style:{"background-color":"#9b293d","border-width":3,"border-color":"#9b293d"}},{selector:"edge",style:{"width":2,"line-color":"#5d6b7b","target-arrow-color":"#5d6b7b","target-arrow-shape":"triangle","curve-style":"bezier"}},{selector:"edge[change = 'added']",style:{"line-color":"#1c7c54","target-arrow-color":"#1c7c54"}},{selector:"edge[change = 'removed']",style:{"line-color":"#9b293d","line-style":"dashed","target-arrow-color":"#9b293d"}},{selector:":selected",style:{"background-color":"#f0a000","line-color":"#f0a000","target-arrow-color":"#f0a000"}}]});
    state.cy.on("tap", "node", (event) => { const node = nodesForMode().find((item) => item.id === event.target.id()); state.returnFocus = null; details(node, "node", node._change); });
    state.cy.on("tap", "edge", (event) => { const edge = edgesForMode().find((item) => item.id === event.target.id()); details(edge, "edge", edgeIds.get(edge.id) || "unchanged"); });
  }
  function refresh() { items(); draw(); details(null); evidenceNotes(); }
  function options() { const values = [...new Set(nodesForMode().map((node) => node.parent).filter(Boolean))].sort(); $("component").replaceChildren(new Option("All components", ""), ...values.map((value) => new Option(value, value))); }
  document.querySelectorAll("[data-mode]").forEach((button) => button.addEventListener("click", () => { state.mode = button.dataset.mode; document.querySelectorAll("[data-mode]").forEach((b) => b.setAttribute("aria-pressed", String(b === button))); options(); refresh(); }));
  $("component").addEventListener("change", (event) => { state.component = event.target.value; refresh(); });
  $("search").addEventListener("input", (event) => { state.search = event.target.value.toLowerCase(); refresh(); });
  $("reset").addEventListener("click", () => { state.component=""; state.search=""; $("component").value=""; $("search").value=""; if (state.cy) state.cy.fit(undefined,32); refresh(); });
  $("zoom-in").addEventListener("click", () => { if (state.cy) state.cy.zoom({level:state.cy.zoom() * 1.2, renderedPosition:{x:$("graph").clientWidth / 2,y:$("graph").clientHeight / 2}}); });
  $("zoom-out").addEventListener("click", () => { if (state.cy) state.cy.zoom({level:state.cy.zoom() / 1.2, renderedPosition:{x:$("graph").clientWidth / 2,y:$("graph").clientHeight / 2}}); });
  [["pan-left",-80,0],["pan-right",80,0],["pan-up",0,-80],["pan-down",0,80]].forEach(([id,x,y]) => $(id).addEventListener("click", () => { if (state.cy) state.cy.panBy({x,y}); }));
  $("details").addEventListener("keydown", (event) => { if (event.key === "Escape" && state.returnFocus) { event.preventDefault(); state.returnFocus.focus(); } });
  summarize(); options(); refresh();
})();
"""


def render_html(packet: dict) -> bytes:
    """Return a self-contained, offline, accessible architecture report."""
    if not isinstance(packet, dict):
        raise TypeError("packet must be a dictionary")
    cytoscape = _read_asset()
    packet_json = _json_for_script(_viewer_packet(packet))
    csp = "; ".join(
        (
            "default-src 'none'",
            f"script-src '{_csp_hash(cytoscape)}' '{_csp_hash(_APP_JS)}'",
            f"style-src '{_csp_hash(_CSS)}'",
            "img-src 'none'",
            "connect-src 'none'",
            "font-src 'none'",
            "media-src 'none'",
            "object-src 'none'",
            "base-uri 'none'",
            "form-action 'none'",
            "frame-ancestors 'none'",
        )
    )
    html = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{csp}"><title>Architecture evidence report</title><style>{_CSS}</style></head>
<body><a class="skip" href="#evidence-list">Skip graph to keyboard evidence list</a><header><h1>Architecture evidence report</h1><p class="lede">Offline review aid. It displays evidence; it does not approve a change.</p></header>
<p id="overall" class="status" role="status" aria-live="polite">Loading report…</p><main>
<section class="identity" aria-label="Evidence identity"><div class="card"><span class="label">Baseline source</span><span id="baseline-id"></span></div><div class="card"><span class="label">Candidate source</span><span id="candidate-id"></span></div><div class="card"><span class="label">Policy result</span><span id="policy-result"></span></div></section>
<section class="controls" aria-label="Report controls"><div class="control"><span class="label">Graph mode</span><div class="modes" role="group" aria-label="Graph mode"><button type="button" data-mode="baseline" aria-pressed="false">Baseline</button><button type="button" data-mode="candidate" aria-pressed="false">Candidate</button><button type="button" data-mode="delta" aria-pressed="true">Delta</button></div></div><label class="control"><span class="label">Component</span><select id="component"></select></label><label class="control"><span class="label">Search evidence</span><input id="search" type="search" autocomplete="off" placeholder="Module, source, finding"></label><div class="control"><span class="label">Graph navigation</span><div class="modes" role="group" aria-label="Graph navigation"><button id="zoom-in" type="button">Zoom in</button><button id="zoom-out" type="button">Zoom out</button><button id="pan-left" type="button">Pan left</button><button id="pan-right" type="button">Pan right</button><button id="pan-up" type="button">Pan up</button><button id="pan-down" type="button">Pan down</button></div></div><button id="reset" type="button">Reset view</button></section>
<section class="workspace" aria-label="Graph and evidence details"><div id="graph" class="graph" role="img" aria-label="Interactive dependency graph. Equivalent evidence is available in the keyboard list below."></div><aside id="details" class="details" tabindex="-1" aria-live="polite" aria-label="Evidence details"><h2>Details</h2><p>Choose a node or dependency to inspect its evidence. Press Escape to return to the selected list item.</p></aside></section>
<section class="list-wrap" aria-labelledby="notes-heading"><h2 id="notes-heading">Findings, limitations, and inventory</h2><ul id="notes" class="items"></ul></section><section id="evidence-list" class="list-wrap" tabindex="-1"><h2>Keyboard evidence list</h2><p class="lede">Dependencies use text labels for added, removed, and unchanged state.</p><ul id="items" class="items"></ul></section></main>
<script id="packet-data" type="application/json">{packet_json}</script><script>{cytoscape}</script><script>{_APP_JS}</script></body></html>'''
    rendered = html.encode("utf-8")
    if len(rendered) > _MAX_REPORT_BYTES:
        raise ValueError("rendered report exceeds 10 MiB safety limit")
    return rendered
