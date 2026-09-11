"""Behavior checks for the standalone architecture evidence report."""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from scripts.architecture_evidence.report import render_html


def _snapshot(digest: str, lines: list[str]) -> dict:
    return {
        "source": {"digest": digest},
        "sources": {"cli/example.py": {"sha256": "a" * 64, "lines": lines}},
        "graph": {
            "nodes": [
                {
                    "id": "python:cli.example",
                    "label": "example",
                    "parent": "component:cli",
                    "path": "cli/example.py",
                    "language": "python",
                }
            ],
            "edges": [
                {
                    "id": "edge-1",
                    "from": "python:cli.example",
                    "to": "python:cli.target",
                    "kind": "direct-import",
                    "sources": [
                        {"path": "cli/example.py", "start_line": 1, "end_line": 1}
                    ],
                }
            ],
        },
        "quality": {
            "status": "available",
            "records": [
                {
                    "id": "python:cli.example",
                    "complexity": {"value": 5},
                    "coverage": {"covered": 1, "total": 1},
                }
            ],
        },
    }


def _packet(label: str = "example") -> dict:
    baseline = _snapshot("baseline-digest", ["from cli.target import value"])
    candidate = _snapshot("candidate-digest", ["from cli.target import value"])
    candidate["graph"]["nodes"][0]["label"] = label
    return {
        "schema_version": 1,
        "kind": "packet",
        "baseline": baseline,
        "candidate": candidate,
        "delta": {
            "added_edges": [candidate["graph"]["edges"][0]],
            "removed_edges": [],
            "unchanged_edges": [],
            "new_cycles": [],
            "baseline_cycles": [],
        },
        "policy_result": "pass",
        "overall_result": "inconclusive",
        "findings": [],
        "gaps": [],
    }


class ArchitectureReportTests(unittest.TestCase):
    def test_report_is_self_contained_and_offline(self) -> None:
        html = render_html(_packet()).decode("utf-8")
        self.assertIn("cytoscape", html)
        self.assertIn("Content-Security-Policy", html)
        self.assertIn("connect-src 'none'", html)
        self.assertIn("Keyboard evidence list", html)
        self.assertNotRegex(html, r"(?:src|href)=['\"]https?://")
        self.assertIn("candidate-digest", html)
        self.assertIn('"overall_result":"inconclusive"', html)

    def test_hostile_packet_text_stays_inert_json(self) -> None:
        hostile = "</script><img src=x onerror=alert(1)>"
        html = render_html(_packet(hostile)).decode("utf-8")
        self.assertNotIn(hostile, html)
        self.assertIn("\\u003c/script\\u003e", html)
        self.assertIn("textContent", html)
        self.assertIn("base-uri 'none'", html)

    def test_vendored_asset_matches_manifest(self) -> None:
        assets = (
            Path(__file__).parents[1] / "scripts" / "architecture_evidence" / "assets"
        )
        manifest = json.loads((assets / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["cytoscape"]["sha256"],
            hashlib.sha256((assets / "cytoscape.min.js").read_bytes()).hexdigest(),
        )
        self.assertTrue((assets / manifest["cytoscape"]["license"]).is_file())

    def test_non_mapping_packet_is_rejected(self) -> None:
        with self.assertRaises(TypeError):
            render_html([])  # type: ignore[arg-type]

    def test_delta_keeps_removed_nodes_and_marks_truncated_source(self) -> None:
        packet = _packet()
        packet["baseline"]["graph"]["nodes"].append(
            {
                "id": "python:cli.removed",
                "label": "removed",
                "parent": "component:cli",
                "path": "cli/removed.py",
                "language": "python",
            }
        )
        packet["baseline"]["sources"]["cli/removed.py"] = {
            "sha256": "b" * 64,
            "lines": ["pass"] * 201,
        }
        html = render_html(packet).decode("utf-8")
        self.assertIn("previous.forEach", html)
        self.assertIn('_change:"removed"', html)
        self.assertIn("Source drilldown is incomplete", html)

    def test_packet_sections_and_quality_path_matching_are_present(self) -> None:
        packet = _packet()
        packet["baseline"]["config"] = {"quality": {"required": False}}
        packet["candidate"]["config"] = {"quality": {"required": False}}
        packet["candidate"]["quality"]["records"][0].update(
            {
                "id": "python:cli/example.py:read_example",
                "path": "cli/example.py",
                "symbol": "read_example",
            }
        )
        packet["candidate"]["tools"] = {
            "capabilities": {"dynamic_imports": "unsupported"}
        }
        packet["findings"] = [
            {"id": "finding-1", "kind": "forbidden-edge", "message": "boundary crossed"}
        ]
        packet["gaps"] = ["missing optional detail"]
        packet["delta"]["baseline_cycles"] = [{"members": ["python:cli.example"]}]
        html = render_html(packet).decode("utf-8")
        self.assertIn("Findings, limitations, and inventory", html)
        self.assertIn("item.path === record.path", html)
        self.assertIn("Baseline cycle ledger", html)
        self.assertIn("Graph scope: static internal direct imports only", html)
        self.assertIn(
            "Required quality evidence is disabled; this is not a full-pilot pass", html
        )

    def test_renderer_keeps_edge_endpoints_and_offers_keyboard_graph_controls(
        self,
    ) -> None:
        html = render_html(_packet()).decode("utf-8")
        self.assertIn("function visibleEvidence()", html)
        self.assertIn("ids.add(edge.from); ids.add(edge.to)", html)
        self.assertNotIn("parent:node.parent", html)
        for control in (
            "zoom-in",
            "zoom-out",
            "pan-left",
            "pan-right",
            "pan-up",
            "pan-down",
        ):
            self.assertIn(f'id="{control}"', html)
        self.assertIn("state.returnFocus.focus()", html)

    def test_renderer_projects_sensitive_packet_fields_out_of_html(self) -> None:
        packet = _packet()
        packet["baseline"]["config"] = {
            "tach_executable": "/Users/example/private/tach",
            "quality": {"required": True},
        }
        packet["approval"] = {
            "approver": "engineer",
            "plan_text": "private plan /Users/example",
            "events_text": "private event",
            "plan_file": "private-plan.md",
        }
        packet["artifacts"] = [{"path": "/private/raw/log", "sha256": "z" * 64}]
        html = render_html(packet).decode("utf-8")
        self.assertIn('"approver":"engineer"', html)
        self.assertNotIn("/Users/example/private/tach", html)
        self.assertNotIn("private plan /Users/example", html)
        self.assertNotIn("private event", html)
        self.assertNotIn("/private/raw/log", html)
