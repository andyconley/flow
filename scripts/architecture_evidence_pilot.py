#!/usr/bin/env python3
"""Isolated architecture evidence pilot. Not an installed Flow command."""

from __future__ import annotations
import argparse
from pathlib import Path
import sys
import os
import tempfile
from architecture_evidence.model import (
    EvidenceError,
    canonical,
    digest,
    load_packet,
    read_json,
    value_digest,
    write_json,
)
from architecture_evidence.snapshot import collect, compare, source_files


def emit(value):
    print(canonical(value).decode(), end="")


class PilotParser(argparse.ArgumentParser):
    def error(self, message):
        emit(
            {
                "operation": None,
                "operation_status": "invalid-invocation",
                "error": message,
            }
        )
        raise SystemExit(2)


def main(argv=None):
    parser = PilotParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--source", required=True)
    c.add_argument("--config", required=True)
    c.add_argument("--out", required=True)
    c = sub.add_parser("compare")
    c.add_argument("--baseline", required=True)
    c.add_argument("--candidate", required=True)
    c.add_argument("--policy", required=True)
    c.add_argument("--out", required=True)
    c = sub.add_parser("render")
    c.add_argument("--packet", required=True)
    c.add_argument("--out", required=True)
    c = sub.add_parser("verify")
    c.add_argument("--packet", required=True)
    c.add_argument("--candidate", required=True)
    c.add_argument("--report", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "collect":
            try:
                config = read_json(args.config)
                if not isinstance(config, dict):
                    raise ValueError("config must be object")
                if not Path(args.source).is_dir():
                    raise ValueError("source directory does not exist")
                if (
                    not isinstance(config.get("source_roots"), list)
                    or not config["source_roots"]
                ):
                    raise ValueError("source_roots must be nonempty list")
                if not isinstance(config.get("quality"), dict):
                    raise ValueError("quality must be an object")
                for key in ("enabled", "required"):
                    if not isinstance(config["quality"].get(key), bool):
                        raise ValueError("quality enabled/required must be boolean")
            except (EvidenceError, ValueError, TypeError) as e:
                emit(
                    {
                        "operation": "collect",
                        "operation_status": "invalid-invocation",
                        "error": str(e),
                    }
                )
                return 2
            s = collect(args.source, config, args.out)
            gaps = s["gaps"] + s["graph"].get("unresolved", [])
            if (
                s["config"].get("quality", {}).get("required", True)
                and s["quality"]["status"] != "available"
            ):
                gaps += s["quality"].get("gaps") or ["quality unavailable"]
            emit(
                {
                    "operation": "collect",
                    "operation_status": "inconclusive" if gaps else "complete",
                    "source_digest": s["source"]["digest"],
                    "out": args.out,
                }
            )
            return 3 if gaps else 0
        if args.command == "compare":
            p = compare(args.baseline, args.candidate, args.policy, args.out)
            emit(
                {
                    "operation": "compare",
                    "operation_status": "complete",
                    **{k: p[k] for k in ("policy_result", "overall_result", "gaps")},
                    "out": args.out,
                }
            )
            return {"pass": 0, "fail": 1, "inconclusive": 3}[p["overall_result"]]
        p = load_packet(args.packet)
        if args.command == "render":
            from architecture_evidence.report import render_html

            path = Path(args.out)
            receipt = path.with_suffix(path.suffix + ".receipt.json")
            if path.exists() or receipt.exists():
                raise EvidenceError("output already exists")
            data = render_html(p)
            if isinstance(data, str):
                data = data.encode()
            if len(data) > 10 * 1024 * 1024:
                raise EvidenceError("report exceeds 10 MiB limit")
            path.parent.mkdir(parents=True, exist_ok=True)
            assets = (
                Path(__file__).parent / "architecture_evidence/assets/manifest.json"
            )
            binding = {
                "schema_version": 1,
                "packet_digest": digest(
                    (Path(args.packet) / "packet.json").read_bytes()
                ),
                "report_digest": digest(data),
                "assets_digest": digest(assets.read_bytes()),
                "viewer_digest": digest(
                    (assets.parent / "cytoscape.min.js").read_bytes()
                ),
            }
            # Publish complete bytes only. The receipt is the final completion marker;
            # an interrupted pair is explicitly unverifiable, never a successful packet.
            with tempfile.TemporaryDirectory(prefix=".report-", dir=path.parent) as tmp:
                staged = Path(tmp) / "report"
                staged.write_bytes(data)
                staged_receipt = Path(tmp) / "receipt"
                staged_receipt.write_bytes(canonical(binding))
                os.link(staged, path)
                try:
                    os.link(staged_receipt, receipt)
                except Exception:
                    path.unlink()
                    raise
            emit(
                {
                    "operation": "render",
                    "operation_status": "complete",
                    "overall_result": p["overall_result"],
                    "out": str(path),
                }
            )
            return 0
        path = Path(args.report)
        receipt = read_json(path.with_suffix(path.suffix + ".receipt.json"))
        assets = Path(__file__).parent / "architecture_evidence/assets/manifest.json"
        if (
            receipt.get("packet_digest")
            != digest((Path(args.packet) / "packet.json").read_bytes())
            or receipt.get("report_digest") != digest(path.read_bytes())
            or receipt.get("assets_digest") != digest(assets.read_bytes())
            or receipt.get("viewer_digest")
            != digest((assets.parent / "cytoscape.min.js").read_bytes())
        ):
            raise EvidenceError("report binding mismatch")
        if (
            value_digest(source_files(Path(args.candidate), p["candidate"]["config"]))
            != p["candidate"]["source"]["digest"]
        ):
            raise EvidenceError("candidate identity mismatch")
        emit(
            {
                "operation": "verify",
                "operation_status": "complete",
                "overall_result": p["overall_result"],
                "policy_result": p["policy_result"],
            }
        )
        return 0
    except (
        EvidenceError,
        OSError,
        KeyError,
        TypeError,
        ValueError,
        RuntimeError,
        AttributeError,
        IndexError,
    ) as e:
        emit(
            {
                "operation": args.command,
                "operation_status": "inconclusive",
                "error": str(e),
            }
        )
        return 3


if __name__ == "__main__":
    sys.exit(main())
