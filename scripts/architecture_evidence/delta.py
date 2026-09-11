"""Language-neutral direct-edge comparison and cyclic-edge analysis."""


def cyclic_edges(graph):
    adjacency = {n["id"]: [] for n in graph["nodes"]}
    for e in graph["edges"]:
        adjacency[e["from"]].append(e["to"])
    index = {}
    low = {}
    stack = []
    active = set()
    components = []

    def visit(v):
        index[v] = low[v] = len(index)
        stack.append(v)
        active.add(v)
        for w in adjacency[v]:
            if w not in index:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in active:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            members = []
            while True:
                w = stack.pop()
                active.remove(w)
                members.append(w)
                if w == v:
                    break
            members.sort()
            member_set = set(members)
            edges = sorted(
                e["id"]
                for e in graph["edges"]
                if e["from"] in member_set and e["to"] in member_set
            )
            if len(members) > 1 or any(
                e["from"] == v == e["to"] for e in graph["edges"]
            ):
                components.append({"members": members, "edges": edges})

    for v in sorted(adjacency):
        if v not in index:
            visit(v)
    return sorted(components, key=lambda c: c["members"])


def compare_graphs(baseline, candidate):
    b = {e["id"]: e for e in baseline["edges"]}
    c = {e["id"]: e for e in candidate["edges"]}
    old = cyclic_edges(baseline)
    new = cyclic_edges(candidate)
    old_ids = {x for s in old for x in s["edges"]}
    return {
        "added_edges": [c[k] for k in sorted(c.keys() - b.keys())],
        "removed_edges": [b[k] for k in sorted(b.keys() - c.keys())],
        "unchanged_edges": [c[k] for k in sorted(c.keys() & b.keys())],
        "new_cycles": [s for s in new if set(s["edges"]) - old_ids],
        "baseline_cycles": old,
    }
