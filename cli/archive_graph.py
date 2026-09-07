"""Context-scoped supersession, evaluated before candidate filtering."""
from archive_model import qualified


def resolve_graph(sources):
    records, source_order, unknown, diagnostics = {}, {}, set(), []
    for position, source in enumerate(sources):
        if source.get("source_id"):
            source_order[source["source_id"]] = position
        for row in source.get("records", []):
            records[row["qualified_id"]] = row
            # Prose failures are visible without invalidating independent,
            # verified closure and supersession controls.
            diagnostics.extend({"qualified_id": row["qualified_id"], **item}
                               for item in row.get("diagnostics", []))
    # Incomplete child contexts can carry overrides to any ancestor, never siblings.
    for position, source in enumerate(sources):
        if source.get("state") not in {"ready"}:
            for identity, row in records.items():
                if source_order.get(row["identity"]["source_id"], -1) >= position:
                    unknown.add(identity)
    unknown.update(key for key, row in records.items() if row.get("closure_status") != "anchored")
    edges = {}
    for identity, row in records.items():
        targets = []
        for edge in row.get("declarations", {}).get("supersedes", []):
            target = None
            try:
                target = qualified(edge["target"])
                if target == identity or target not in records or edge.get("whole_run") is not True:
                    raise ValueError("self, unresolved or partial edge")
                if source_order[edge["target"]["source_id"]] < source_order[row["identity"]["source_id"]]:
                    raise ValueError("downward supersession is not allowed")
                if row.get("declaration_status") != "anchored":
                    raise ValueError("declaration lacks matching closure anchor")
                targets.append(target)
            except (ValueError, KeyError, TypeError) as error:
                unknown.add(identity)
                if target in records:
                    unknown.add(target)
                diagnostics.append({"code": "invalid_supersession", "qualified_id": identity, "detail": str(error)})
        if row.get("declaration_status") == "unverified":
            start = source_order[row["identity"]["source_id"]]
            unknown.update(k for k, v in records.items() if source_order[v["identity"]["source_id"]] >= start)
        edges[identity] = targets
    # Reachability per origin avoids recursion limits and identifies cycle members.
    cycles = set()
    for origin in edges:
        pending, visited = list(edges[origin]), set()
        while pending:
            node = pending.pop()
            if node == origin:
                cycles.add(origin)
                break
            if node not in visited:
                visited.add(node)
                pending.extend(edges.get(node, []))
    unknown.update(cycles)
    while True:
        propagated = unknown | {target for origin in unknown for target in edges.get(origin, [])}
        if propagated == unknown:
            break
        unknown = propagated
    superseded, replaced_by = set(), {}
    for origin, targets in edges.items():
        if origin in unknown:
            unknown.update(targets)
            continue
        for target in targets:
            superseded.add(target)
            replaced_by.setdefault(target, []).append(origin)
    statuses = {key: {"status": "unknown" if key in unknown else "superseded" if key in superseded else "current", "superseded_by": sorted(replaced_by.get(key, [])), "supersedes": edges.get(key, [])} for key in records}
    return {"records": statuses, "diagnostics": diagnostics + ([{"code": "supersession_cycle", "members": sorted(cycles)}] if cycles else [])}
