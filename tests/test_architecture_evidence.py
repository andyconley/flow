"""Behavior contracts for portable evidence."""

import copy, json, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from architecture_evidence.model import *
from architecture_evidence.delta import compare_graphs
from architecture_evidence.policy import evaluate, approval_gaps
from architecture_evidence.snapshot import compare

ROOT = Path(__file__).resolve().parents[1]
POLICY = read_json(ROOT / "tests/fixtures/architecture_evidence/policy-v1.json")


def approval():
    text = "watermark must not import either collector or harvest"
    a = dict(
        policy_digest=value_digest(POLICY),
        plan_text=text,
        plan_digest=digest(text.encode()),
        approved_rules=POLICY["rules"],
        approver="fixture",
        event=dict(
            event="approve-plan",
            to="plan_approved",
            at="2026-09-11",
            artifacts={"plan": ".flow/runs/fixture/plan.md"},
        ),
    )
    a["events_text"] = json.dumps(a["event"]) + "\n"
    a["plan_file"] = "approved-plan.md"
    a["events_file"] = "approval-events.jsonl"
    return a


def snapshot(edges=(), language="python"):
    names = ("jsonl_watermark", "codex_collector", "harvest")
    sha = digest(b"import example\n")
    files = sorted(
        [dict(path="cli/" + n + ".py", sha256=sha) for n in names],
        key=lambda f: f["path"],
    )
    nodes = [
        dict(
            id=language + ":" + n,
            label=n,
            parent="component:cli",
            language=language,
            path="cli/" + n + ".py",
            sha256=sha,
        )
        for n in names
    ]
    graph = dict(
        nodes=nodes,
        edges=[
            {
                "id": a + ">" + b,
                "from": language + ":" + a,
                "to": language + ":" + b,
                "kind": "direct-import",
                "sources": [dict(path="cli/" + a + ".py", start_line=1, end_line=1)],
            }
            for a, b in edges
        ],
        inventory=[
            dict(path=f["path"], status="processed", reason="fixture") for f in files
        ],
        unresolved=[],
    )
    cfg = dict(source_roots=["cli"], quality=dict(required=False))
    return dict(
        schema_version=1,
        kind="snapshot",
        source=dict(files=files, digest=value_digest(files), revision=None),
        config=cfg,
        config_digest=value_digest(cfg),
        graph=normalize_graph(graph),
        quality=dict(status="unsupported", records=[]),
        gaps=[],
        tools={"fixture": "1"},
        artifacts=[],
        sources={
            f["path"]: dict(
                sha256=sha, text="import example\n", lines=["import example"]
            )
            for f in files
        },
    )


class EvidenceTests(unittest.TestCase):
    def result(self, b, c):
        return evaluate(
            b, c, compare_graphs(b["graph"], c["graph"]), POLICY, approval()
        )

    def test_clean_forbidden_and_inconclusive(self):
        b = snapshot()
        self.assertEqual(self.result(b, b)["overall_result"], "pass")
        c = snapshot([("jsonl_watermark", "codex_collector")])
        self.assertEqual(self.result(b, c)["overall_result"], "fail")
        c["gaps"] = ["missing raw"]
        r = self.result(b, c)
        self.assertEqual(r["overall_result"], "inconclusive")
        self.assertEqual(r["findings"][0]["kind"], "forbidden-edge")

    def test_baseline_ledger(self):
        b = snapshot([("jsonl_watermark", "codex_collector")])
        r = self.result(b, b)
        self.assertEqual(r["findings"][0]["kind"], "baseline-violation")

    def test_new_cycle_and_reduction(self):
        b = snapshot([("harvest", "jsonl_watermark")])
        c = snapshot([("harvest", "jsonl_watermark"), ("jsonl_watermark", "harvest")])
        self.assertEqual(len(compare_graphs(b["graph"], c["graph"])["new_cycles"]), 1)
        self.assertEqual(compare_graphs(c["graph"], b["graph"])["new_cycles"], [])

    def test_added_edge_inside_existing_cycle(self):
        edges = [
            ("harvest", "jsonl_watermark"),
            ("jsonl_watermark", "codex_collector"),
            ("codex_collector", "harvest"),
        ]
        b = snapshot(edges)
        c = snapshot(edges + [("harvest", "codex_collector")])
        self.assertEqual(len(compare_graphs(b["graph"], c["graph"])["new_cycles"]), 1)

    def test_self_cycle(self):
        self.assertEqual(
            len(
                compare_graphs(
                    snapshot()["graph"], snapshot([("harvest", "harvest")])["graph"]
                )["new_cycles"]
            ),
            1,
        )

    def test_nested_order(self):
        g = snapshot([("harvest", "codex_collector")])["graph"]
        h = copy.deepcopy(g)
        h["nodes"].reverse()
        h["inventory"].reverse()
        self.assertEqual(canonical(normalize_graph(g)), canonical(normalize_graph(h)))

    def test_inventory_and_span(self):
        s = snapshot()
        s["graph"]["inventory"].pop()
        with self.assertRaises(EvidenceError):
            validate_snapshot(s)
        s = snapshot([("harvest", "codex_collector")])
        s["graph"]["edges"][0]["sources"][0]["start_line"] = 0
        with self.assertRaises(EvidenceError):
            validate_snapshot(s)

    def test_tampered_source_and_config(self):
        s = snapshot()
        s["sources"]["cli/harvest.py"]["lines"] = ["forged"]
        with self.assertRaises(EvidenceError):
            validate_snapshot(s)
        s = snapshot()
        s["config"]["quality"]["required"] = True
        with self.assertRaises(EvidenceError):
            validate_snapshot(s)

    def test_approval(self):
        a = approval()
        a["approver"] = ""
        self.assertTrue(approval_gaps(POLICY, a))
        a = approval()
        a["approved_rules"] = []
        self.assertTrue(approval_gaps(POLICY, a))

    def test_language(self):
        s = snapshot(
            [("harvest", "codex_collector")], language="typescript:@pkg/opaque"
        )
        validate_snapshot(s)
        self.assertEqual(self.result(s, s)["policy_result"], "pass")

    def test_touched_baseline_requires_disposition(self):
        b = snapshot([("jsonl_watermark", "codex_collector")])
        c = copy.deepcopy(b)
        next(n for n in c["graph"]["nodes"] if n["id"] == "python:jsonl_watermark")[
            "sha256"
        ] = "changed"
        self.assertEqual(self.result(b, c)["overall_result"], "inconclusive")

    def test_rules_are_semantically_ordered(self):
        policy = copy.deepcopy(POLICY)
        policy["rules"].reverse()
        self.assertEqual(value_digest(policy), value_digest(POLICY))
        self.assertFalse(approval_gaps(policy, approval()))

    def test_node_missing_excerpt_is_rejected(self):
        s = snapshot()
        del s["sources"]["cli/harvest.py"]
        with self.assertRaises(EvidenceError):
            validate_snapshot(s)

    def test_packet_integrity(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            for side in ("b", "c"):
                (d / side).mkdir()
                write_json(d / side / "snapshot.json", snapshot())
            write_json(d / "policy.json", POLICY)
            write_json(d / "policy-approval.json", approval())
            (d / "approved-plan.md").write_text(approval()["plan_text"])
            (d / "approval-events.jsonl").write_text(approval()["events_text"])
            compare(d / "b", d / "c", d / "policy.json", d / "packet")
            load_packet(d / "packet")
            with self.assertRaises(EvidenceError):
                compare(d / "b", d / "c", d / "policy.json", d / "packet")
            p = read_json(d / "packet/packet.json")
            p["overall_result"] = "fail"
            write_json(d / "packet/packet.json", p)
            with self.assertRaises(EvidenceError):
                load_packet(d / "packet")


if __name__ == "__main__":
    unittest.main()
