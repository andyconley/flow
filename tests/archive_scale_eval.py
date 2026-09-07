"""Run explicit loose-filter scale measurements; not an acceptance threshold."""
import argparse
import json
from pathlib import Path
import resource
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_archive_resources import ArchiveResourceTests
import archive_query as query
import archive_service as service
from archive_sources import assess_source
from archive_graph import resolve_graph


def measure(count):
    fixture = ArchiveResourceTests()
    fixture.setUp()
    try:
        for number in range(count):
            fixture.add_run(f"work-{number:05d}")
        assert service.backfill(fixture.root, apply=True, yes=True)["state"] == "complete"
        assert query.rebuild(fixture.root)["state"] == "complete"
        started = time.perf_counter()
        source = assess_source(fixture.root, compact=True)
        assessment_seconds = time.perf_counter() - started
        source["distance"] = 0
        graph = resolve_graph([source])
        started = time.perf_counter()
        with query._stream_ranked([source], graph, "SQLite", None, None, None, False, 5) as (ordered, total, uncertain):
            rows = list(ordered)
        ranking_seconds = time.perf_counter() - started
        assert total == count and uncertain == 0 and len(rows) == min(count, 5)
        return {"records": count, "query": "SQLite", "filters": "none", "source_assessment_seconds": assessment_seconds,
                "stream_rank_and_verified_prefix_seconds": ranking_seconds, "retained_prefix": len(rows), "total_matches": total,
                "process_peak_rss_platform_units": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                "rss_scope": "whole process including fixture generation and rebuild; bytes on macOS, KiB on Linux",
                "python": sys.version, "platform": sys.platform}
    finally:
        fixture.doCleanups()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=int, default=1000)
    args = parser.parse_args()
    if args.records < 1:
        parser.error("records must be positive")
    print(json.dumps(measure(args.records), indent=2))
