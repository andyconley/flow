"""Argparse registration and presentation for archive operations."""
import json
import archive_legacy
from pathlib import Path
from fsutil import repo_root
from archive_query import EXITS, rebuild, search, serialized, pack, minimum_budget
from archive_service import backfill, mutate


def register(sub):
    archive = sub.add_parser("archive", help="inspect, retrieve and repair archived and reviewed legacy decisions")
    commands = archive.add_subparsers(dest="archive_action", required=True)
    search = commands.add_parser("search", help="bounded ancestor-aware BM25 retrieval; requires install/doctor FTS5 preflight")
    search.add_argument("query")
    search.add_argument("--lane", choices=("define", "solution"), default="define")
    scope = search.add_mutually_exclusive_group()
    scope.add_argument("--source", action="append")
    scope.add_argument("--current-only", action="store_true")
    search.add_argument("--component")
    search.add_argument("--work-type")
    search.add_argument("--since")
    search.add_argument("--include-superseded", action="store_true")
    search.add_argument("--top-k", type=int)
    search.add_argument("--max-output-bytes", type=int, help=f"full UTF-8 response bytes, minimum {minimum_budget()}; not model tokens")
    search.add_argument("--json", action="store_true", help="canonical JSON (also the default bounded block format)")
    imports = commands.add_parser("import", help="review legacy evidence without fabricating canonical closure")
    import_commands = imports.add_subparsers(dest="import_action", required=True)
    preview = import_commands.add_parser("preview", help="read-only legacy candidates and evidence; never grants approval")
    preview.add_argument("work_id", nargs="?")
    preview.add_argument("--json", action="store_true")
    review = import_commands.add_parser("review", help="validate a reviewer record; writes require --apply --yes and its current fingerprint")
    review.add_argument("work_id")
    review.add_argument("--record", required=True)
    review.add_argument("--apply", action="store_true")
    review.add_argument("--yes", action="store_true")
    review.add_argument("--json", action="store_true")
    rescan = import_commands.add_parser("rescan", help="repair one legacy abstract without changing review authority; read-only by default")
    rescan.add_argument("work_id")
    rescan.add_argument("--base-fingerprint")
    rescan.add_argument("--apply", action="store_true")
    rescan.add_argument("--yes", action="store_true")
    rescan.add_argument("--json", action="store_true")
    backfill = commands.add_parser("backfill", help="preview canonical archived repairs; legacy import excluded")
    backfill.add_argument("--rescan", action="store_true")
    backfill.add_argument("--work-id", action="append")
    backfill.add_argument("--apply", action="store_true")
    backfill.add_argument("--yes", action="store_true")
    backfill.add_argument("--json", action="store_true")
    for name in ("declare", "refine"):
        parser = commands.add_parser(name, help="preview field-owned mutation; apply requires current base digest and --yes")
        parser.add_argument("work_id")
        parser.add_argument("--input", required=True)
        parser.add_argument("--base-digest", required=True)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--yes", action="store_true")
        parser.add_argument("--json", action="store_true")
    inspect = commands.add_parser("inspect", help="inspect qualified archive evidence; unknown is never current")
    inspect.add_argument("qualified_id")
    inspect.add_argument("--json", action="store_true")
    index = sub.add_parser("index", help="manage disposable per-overlay archive projection")
    index_sub = index.add_subparsers(dest="index_action", required=True)
    rebuild = index_sub.add_parser("rebuild", help="rebuild current overlay only; never generates canonical prose or identities")
    rebuild.add_argument("--json", action="store_true")


def dispatch(args):
    from archive_query import EXITS, rebuild, search, serialized, pack, minimum_budget
    from archive_service import backfill, mutate
    root = repo_root()
    try:
        if args.command == "index":
            result = rebuild(root)
        elif args.archive_action == "search":
            result = search(root, args.query, lane=args.lane, sources=args.source, current_only=args.current_only, component=args.component, work_type=args.work_type, since=args.since, include_superseded=args.include_superseded, top_k=args.top_k, max_output_bytes=args.max_output_bytes)
        elif args.archive_action == "import":
            if args.import_action == "preview":
                result = archive_legacy.preview(root, args.work_id)
            elif args.import_action == "review":
                result = archive_legacy.review(root, args.work_id, args.record, apply=args.apply, yes=args.yes)
            else:
                result = archive_legacy.rescan(root, args.work_id, base_fingerprint=args.base_fingerprint, apply=args.apply, yes=args.yes)
        elif args.archive_action == "backfill":
            result = backfill(root, rescan=args.rescan, apply=args.apply, yes=args.yes, work_ids=args.work_id)
        elif args.archive_action in {"declare", "refine"}:
            result = mutate(root, args.work_id, args.archive_action, json.loads(Path(args.input).read_text()), args.base_digest, args.apply, args.yes)
        else:
            from archive_model import qualified
            source_id, separator, work_id = args.qualified_id.partition(":")
            if not separator or ":" in work_id:
                raise ValueError("inspect requires UUID:work-id")
            qualified({"source_id": source_id, "work_id": work_id})
            from archive_sources import discover_context, assess_source
            from archive_graph import resolve_graph
            context = discover_context(root)
            for source in context:
                if source["state"] == "ready":
                    source.update(assess_source(Path(source["root"])))
            graph = resolve_graph(context)
            rows = [r for s in context for r in s.get("records", []) if r["qualified_id"] == args.qualified_id and r.get("envelope") and r["envelope"].get("generated")]
            for row in rows:
                row.update(graph["records"][row["qualified_id"]])
                if not row.get("content_current"):
                    row["status"] = "unknown"
                    graph["diagnostics"].append({"qualified_id": row["qualified_id"], "code": "content_unverified", "remedy": "inspect source evidence and run flow archive backfill --rescan"})
            result = pack({"state": "partial" if any(r["status"] == "unknown" for r in rows) else "complete" if rows else "unavailable", "reason": "explicit_inspection", "diagnostics": graph["diagnostics"]}, rows, 1, 32768)
    except (OSError, ValueError, KeyError, TypeError) as error:
        result = {"state": "invalid_request", "reason": str(error)}
    print(serialized(result), end="")
    return result.get("exit_code", EXITS.get(result["state"], 0 if result["state"] == "preview" else 4))
