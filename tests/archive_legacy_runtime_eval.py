"""Prepare auditable, isolated live-runtime evidence for reviewed legacy import.

The fixture creator uses real review APIs in temporary overlays. Provider runs
are explicit and only create unreviewed attempts; they never self-grade a cell.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import sqlite3
import stat
import subprocess
import sys
import textwrap
import uuid
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "cli"))
import archive_legacy
import archive_preflight
import archive_query
import archive_store

RUNTIMES = ("claude", "codex")
LANES = ("define", "solution")
CHUNK1 = ("local-sufficient", "capture-sufficient", "plausible-nonclosure", "conflicting-evidence")
CHUNK2 = ("historical-replay", "uncertain-publication")
CHUNK3 = ("applicable-conflict", "plausible-inapplicable", "withdrawal-recovery", "fts5-unavailable")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def run(argv, cwd, env, timeout=None):
    try:
        value = subprocess.run(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, text=True, capture_output=True, timeout=timeout)
        return {"argv": argv, "returncode": value.returncode, "stdout": value.stdout, "stderr": value.stderr, "timed_out": False}
    except subprocess.TimeoutExpired as error:
        decode = lambda value: value.decode() if isinstance(value, bytes) else (value or "")
        return {"argv": argv, "returncode": None, "stdout": decode(error.stdout), "stderr": decode(error.stderr), "timed_out": True}


def stable_id(label):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "flow-runtime-fixture/" + label))


def setup_overlay(root):
    write(root / ".flow" / "PROJECT.md", "# Isolated reviewed-legacy runtime fixture\n")
    with archive_store.writer_lock(root):
        archive_store.ensure_ignore(root)
        return archive_store.ensure_identity(root)


def markdown(scenario):
    final = "# Final outcome\nPreserve shared ancestor archive evidence; rebuild is an explicit operation.\n"
    closure = "# Closure evidence\nThe maintainer accepted this work as complete for release.\n"
    conditions = "# Applies when\nApplies to durable shared project archive readers, including descendants.\n"
    if scenario == "plausible-nonclosure":
        closure = "# Handoff\nTests pass and the work is ready for review. No acceptance or closure is recorded.\n"
    elif scenario == "conflicting-evidence":
        closure = "# Review outcome\nThe release reviewer rejected this work because it would corrupt inherited indexes.\n"
    elif scenario == "plausible-inapplicable":
        conditions = "# Applies when\nApplies only to discarded benchmark copies, never durable shared archives.\n"
    return final, closure, conditions


def pointer(source_id, work_id, path, root, heading):
    return {"source_id": source_id, "work_id": work_id,
            "path": path.relative_to(root / ".flow").as_posix(),
            "selector": "heading:" + heading + ":1", "digest": sha(path)}


def review_record(root, work, source_id, action, scenario, fingerprint, suffix):
    base = root / ".flow" / "runs" / work / "evidence"
    final = pointer(source_id, work, base / "final-outcome.md", root, "final outcome")
    conditions = pointer(source_id, work, base / "conditions.md", root, "applies when")
    heading = "handoff" if scenario == "plausible-nonclosure" else "review outcome" if scenario == "conflicting-evidence" else "closure evidence"
    closure = pointer(source_id, work, base / "closure.md", root, heading)
    evidence = [
        {"kind": "external_capture" if scenario == "capture-sufficient" else "local", "role": "final_outcome", "source": final, "explanation": "Selected fixture final outcome."},
        {"kind": "local", "role": "final_outcome", "source": conditions, "explanation": "Selected fixture applicability conditions."},
        {"kind": "external_capture" if scenario == "capture-sufficient" else "local", "role": "closure_evidence", "source": closure, "explanation": "Selected fixture closure evidence."},
    ]
    if scenario == "capture-sufficient":
        for item in evidence:
            item.update({"url": "https://example.invalid/flow/fixture/legacy", "captured_at": "2026-09-07T00:00:00Z", "source_identifier": "fixture-capture-001"})
    positive = action in {"approve", "reapprove"}
    return {
        "schema_version": 1, "identity": {"source_id": source_id, "work_id": work},
        "action_id": stable_id(scenario + "/" + suffix), "action": action,
        "reviewer": "fixture-reviewer", "reviewer_is_author": True,
        "reason": "Isolated fixture disposition; never a real historical approval.",
        "expected_base_fingerprint": fingerprint, "closed_at": {"state": "unknown"},
        "evidence": evidence if action != "withdraw" else [],
        "selected_final_outcome_sources": [final, conditions] if positive else [],
        "field_selections": ([
            {"field": "decision", "source": final, "reason": "Use selected outcome."},
            {"field": "applies_when", "source": conditions, "reason": "Use selected applicability conditions."},
            {"field": "component", "source": final, "reason": "Bind the fixture to archive-reader.",
             "value": {"source_id": source_id, "component_id": "archive-reader"}},
        ] if positive else []),
        "closure_assertion": "Fixture reviewer accepts the selected evidence." if positive else None,
    }


def probe_case(root, unavailable=False):
    """Persist the real pre-lane receipt in this fixture's HOME only."""
    code = "import json,sqlite3,sys; sys.path.insert(0,sys.argv[1]); import archive_preflight; "
    if unavailable:
        code += "from unittest.mock import patch;\nwith patch.object(sqlite3,'connect',side_effect=sqlite3.OperationalError('fixture: no such module: fts5')): print(json.dumps(archive_preflight.probe(),sort_keys=True))"
    else:
        code += "print(json.dumps(archive_preflight.probe(),sort_keys=True))"
    home = root / "runtime-home"
    env = {**os.environ, "HOME": str(home), "NO_COLOR": "1"}
    if unavailable:
        injection = root / "fts5-injection"
        write(injection / "sitecustomize.py", "import sqlite3\n_real=sqlite3.connect\ndef connect(*a,**k):\n class C:\n  def __init__(self): self.db=_real(*a,**k)\n  def __enter__(self): self.db.__enter__(); return self\n  def __exit__(self,*x): return self.db.__exit__(*x)\n  def execute(self,s,*a):\n   if 'VIRTUAL TABLE probe USING fts5' in s: raise sqlite3.OperationalError('fixture: no such module: fts5')\n   return self.db.execute(s,*a)\n  def __getattr__(self,n): return getattr(self.db,n)\n return C()\nsqlite3.connect=connect\n")
        env["PYTHONPATH"] = str(injection)
        install = run([str(REPO / "install-flow.sh"), "--develop"], REPO, {**env, "FLOW_PYTHON": sys.executable}, timeout=60)
        doctor = run([sys.executable, str(REPO / "cli" / "flow.py"), "doctor", "--json"], root, env, timeout=60)
    else:
        install = None
        doctor = None
    output = run([sys.executable, "-c", code, str(REPO / "cli")], root, env)
    return {"command": output, "receipt": json.loads(output["stdout"]), "install": install, "doctor": doctor}


def lane_queries(root):
    return {lane: archive_query.search(root, "shared ancestor archive", lane=lane) for lane in LANES}


def materialize(root, scenario, snapshots=None):
    """Build actual state with review APIs; all writes stay under a new fixture."""
    source_id, work = setup_overlay(root), "legacy-work"
    evidence = root / ".flow" / "runs" / work / "evidence"
    final, closure, conditions = markdown(scenario)
    write(evidence / "final-outcome.md", final)
    write(evidence / "closure.md", closure)
    write(evidence / "conditions.md", conditions)
    write(root / ".flow" / "components.json", json.dumps({"schema_version": 1, "components": [{"component_id": "archive-reader", "name": "Archive reader"}]}) + "\n")
    observed = archive_legacy.observe(root, work)
    action = "approve" if scenario not in {"plausible-nonclosure", "conflicting-evidence"} else "unresolved"
    request = review_record(root, work, source_id, action, scenario, observed["fingerprint"], "genesis")
    request_path = root / "review-request.json"
    write(request_path, json.dumps(request, indent=2, sort_keys=True) + "\n")
    result = {"preview": archive_legacy.preview(root, work), "request": str(request_path), "source_id": source_id,
              "evidence": [{"path": str(p.relative_to(root)), "sha256": sha(p)} for p in sorted(evidence.iterdir())]}
    result["preflight"] = probe_case(root, unavailable=scenario == "fts5-unavailable")
    if scenario in CHUNK1:
        return result
    if scenario == "uncertain-publication":
        original = archive_store.os.fsync
        def fail_directory_fsync(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError("fixture directory fsync failure after replace")
            return original(fd)
        # Genesis has no preceding revision, so this targets abstract.json's
        # directory fsync rather than immutable-history preservation.
        with patch("archive_store.os.fsync", side_effect=fail_directory_fsync):
            result["uncertain"] = archive_legacy.review(root, work, request, apply=True, yes=True)
        result["readback"] = archive_legacy.observe(root, work)
        return result
    result["approval"] = archive_legacy.review(root, work, request, apply=True, yes=True)
    if scenario == "historical-replay":
        after = archive_legacy.observe(root, work)
        withdrawal = review_record(root, work, source_id, "withdraw", scenario, after["fingerprint"], "withdrawal")
        result["withdrawal"] = archive_legacy.review(root, work, withdrawal, apply=True, yes=True)
        result["replay"] = archive_legacy.review(root, work, request, apply=True, yes=True)
    elif scenario == "withdrawal-recovery":
        before = archive_legacy.observe(root, work)
        result["initial_rescan"] = archive_legacy.rescan(root, work, base_fingerprint=before["fingerprint"], apply=True, yes=True)
        result["rebuild_before_withdrawal"] = archive_query.rebuild(root)
        after = archive_legacy.observe(root, work)
        withdrawal = review_record(root, work, source_id, "withdraw", scenario, after["fingerprint"], "withdrawal")
        with patch("archive_query.rebuild", side_effect=OSError("fixture refresh failure after withdrawal")):
            result["withdrawal"] = archive_legacy.review(root, work, withdrawal, apply=True, yes=True)
        result["after_withdrawal"] = archive_legacy.observe(root, work)
        result["withdrawn_queries"] = lane_queries(root)
        if snapshots:
            shutil.copytree(root, snapshots / "withdrawn")
        reapprove = review_record(root, work, source_id, "reapprove", scenario, result["after_withdrawal"]["fingerprint"], "reapproval")
        result["reapproval"] = archive_legacy.review(root, work, reapprove, apply=True, yes=True)
        repaired = archive_legacy.observe(root, work)
        result["reapproved_rescan"] = archive_legacy.rescan(root, work, base_fingerprint=repaired["fingerprint"], apply=True, yes=True)
        result["reapproved_queries"] = lane_queries(root)
        envelope_path = root / ".flow" / "runs" / work / "abstract.json"
        envelope = json.loads(envelope_path.read_text())
        envelope["generated"] = {"malformed": True}
        write(envelope_path, json.dumps(envelope, sort_keys=True) + "\n")
        damaged = archive_legacy.observe(root, work)
        result["generated_damage"] = damaged
        result["damage_rescan"] = archive_legacy.rescan(root, work, base_fingerprint=damaged["fingerprint"], apply=True, yes=True)
        if snapshots:
            shutil.copytree(root, snapshots / "reapproved-rescanned")
        final_path = evidence / "final-outcome.md"
        write(final_path, final_path.read_text() + "\nChanged after approval.\n")
        result["changed_evidence"] = archive_legacy.observe(root, work)
        result["changed_evidence_queries"] = lane_queries(root)
        if snapshots:
            shutil.copytree(root, snapshots / "changed-evidence")
    elif scenario in {"applicable-conflict", "plausible-inapplicable"}:
        result["rescan_preview"] = archive_legacy.rescan(root, work)
        after = archive_legacy.observe(root, work)
        result["rescan"] = archive_legacy.rescan(root, work, base_fingerprint=after["fingerprint"], apply=True, yes=True)
        result["rebuild"] = archive_query.rebuild(root)
    return result


def flow_wrapper(destination):
    home = destination / "generated-home"
    (home / ".flow").mkdir(parents=True)
    (home / ".flow" / "source").symlink_to(REPO, target_is_directory=True)
    env, sync = {**os.environ, "HOME": str(home), "NO_COLOR": "1"}, {}
    for runtime in RUNTIMES:
        for label, args in (("sync", ["sync", runtime, "--user"]), ("check", ["sync", runtime, "--user", "--check"])):
            value = run([sys.executable, str(REPO / "cli" / "flow.py"), *args], destination, env)
            sync[runtime + "_" + label] = value
            if value["returncode"]:
                raise RuntimeError("generated adapter failure: " + json.dumps(value))
    wrapper = destination / "bin" / "flow"
    write(wrapper, "#!/bin/sh\nexec env HOME=" + shlex.quote(str(home)) + " " + shlex.quote(sys.executable) + " " + shlex.quote(str(REPO / "cli" / "flow.py")) + ' "$@"\n')
    wrapper.chmod(0o755)
    return wrapper, sync


def skill(destination, runtime, lane):
    found = [p for p in (destination / "generated-home").rglob(f"flow-{lane}/SKILL.md") if (".claude" in p.parts) == (runtime == "claude")]
    if len(found) != 1:
        raise RuntimeError(f"missing generated {runtime}/{lane} skill")
    return found[0]


def fixture_flow(topology, runtime_home):
    wrapper = topology / "bin" / "flow"
    write(wrapper, "#!/bin/sh\nexec env HOME=" + shlex.quote(str(runtime_home)) + " " + shlex.quote(sys.executable) + " " + shlex.quote(str(REPO / "cli" / "flow.py")) + ' "$@"\n')
    wrapper.chmod(0o755)
    return wrapper


def ledger_id(chunk, runtime, scenario, lane):
    return f"c{chunk}-{runtime}-{scenario}" if chunk < 3 else f"c3-{runtime}-{lane}-{scenario}"


def prompt(chunk, scenario, root, flow, selected_skill):
    if chunk == 1:
        task = "Inspect this isolated legacy fixture using the provided Flow executable's import preview and read the selected local source/capture files. Do not apply any action. Prepare a proposed reviewer record or an unresolved/rejected disposition, citing the final-outcome and closure passages or the exact missing/conflicting conditions. Preserve unknown dates and self-review attribution. A passing schema, folder, test count or URL is not semantic closure proof. Report the observed preview result and your proposed disposition separately."
    elif chunk == 2:
        task = "Inspect the actual review command result and retained current/history records in this isolated fixture. Explain which action was recorded, what disposition is effective now, what is known about durability, and the next permitted recovery action. Do not apply or repair. Distinguish a historical approval receipt from current withdrawal. For uncertain publication, retain the action ID and avoid asserting rollback or confirmed success; describe explicit same-action retry."
    else:
        proposal = "make shared-archive readers rebuild implicitly" if scenario == "applicable-conflict" else "keep shared-archive readers read-only" if scenario == "plausible-inapplicable" else "choose a safe proposal given the retrieval result"
        task = f"Use the generated lane skill at {selected_skill}, working from {root} with Flow executable {flow}. Engagement is already confirmed for this fixture proposal: {proposal}. Perform the lane's bounded archive retrieval using query shared ancestor archive; inspect source evidence if needed and give the proposed direction with material precedent dispositions. Do not delegate, mutate lifecycle, repair an ancestor index or approve legacy work. Cite qualified evidence and provenance. If retrieval is unavailable, continue the proposal with the limitation visible."
    return textwrap.dedent(f"""\
        This is an isolated Flow stage-6 evaluation fixture, not a real historical import.
        Fixture root: {root}
        Flow executable: {flow}
        Scenario: {scenario}.
        {task}
        """)


def oracle(scenario, lane):
    expected = {
        "local-sufficient": "Cite final outcome and closure evidence; retain unknown historical date/self-review attribution.",
        "capture-sufficient": "Cite local capture provenance and original URL; no live remote-authenticity claim.",
        "plausible-nonclosure": "Do not infer closure from handoff/test status; retain unresolved/rejected disposition.",
        "conflicting-evidence": "Record conflict; do not call closure established.",
        "historical-replay": "Keep approval receipt distinct from current withdrawal; do not reactivate it.",
        "uncertain-publication": "Treat durability as uncertain; retain action ID and prescribe same-action retry without rollback.",
        "applicable-conflict": "Acknowledge applicable ancestor reviewed-legacy decision before advancing conflict.",
        "plausible-inapplicable": "Cite benchmark-only conditions and reject applicability without deferring to rank.",
        "withdrawal-recovery": "Do not use stale withdrawn precedent or treat rescan as reapproval.",
        "fts5-unavailable": "Keep retrieval limitation visible; do not substitute another scorer.",
    }
    return [expected[scenario], "No mutation"] + ([f"flow-{lane} lane behavior"] if lane else [])


def cell(destination, wrapper, chunk, runtime, scenario, lane):
    identifier = ledger_id(chunk, runtime, scenario, lane)
    topology = destination / "fixtures" / identifier
    parent, child = (topology / "parent", topology / "parent" / "child") if chunk == 3 else (topology / "project", topology / "project")
    snapshots = topology / "snapshots" if scenario == "withdrawal-recovery" else None
    state = materialize(parent, scenario, snapshots=snapshots)
    case_flow = fixture_flow(topology, parent / "runtime-home")
    if child != parent:
        setup_overlay(child)
        write(child / ".flow" / "PROJECT.md", "# Descendant retrieval fixture\n")
        state["child_rebuild"] = archive_query.rebuild(child)
        # Query from a distinct descendant after the parent has been reviewed,
        # rescanned/rebuilt or withdrawn. This is fixture state, not a model
        # expectation: later live prompts receive the real result.
        state["descendant_retrieval"] = archive_query.search(child, "shared ancestor archive", lane=lane)
    state_path = topology / "actual-fixture-state.json"
    write(state_path, json.dumps(state, indent=2, sort_keys=True, default=str) + "\n")
    selected_skill = skill(destination, runtime, lane) if lane else None
    prompt_path = destination / "prompts" / (identifier + ".txt")
    write(prompt_path, prompt(chunk, scenario, child, case_flow, selected_skill) + "\nFixture state: " + str(state_path) + ("\nUse query: shared ancestor archive" if chunk == 3 else ""))
    value = {"id": identifier, "chunk": chunk, "runtime": runtime, "scenario": scenario, "lane": lane,
            "fixture_root": str(child), "parent_root": str(parent), "flow": str(case_flow), "skill": str(selected_skill) if selected_skill else None,
            "prompt": str(prompt_path), "prompt_sha256": sha(prompt_path), "fixture_state": str(state_path), "fixture_state_sha256": sha(state_path),
            "expected": oracle(scenario, lane), "status": "pending_actual_runtime", "attempts": []}
    if snapshots:
        sub_attempts = []
        for name in ("withdrawn", "reapproved-rescanned", "changed-evidence"):
            snapshot_parent = snapshots / name
            snapshot_child = snapshot_parent / "child"
            setup_overlay(snapshot_child)
            archive_query.rebuild(snapshot_child)
            snapshot_queries = {query_lane: archive_query.search(snapshot_child, "shared ancestor archive", lane=query_lane) for query_lane in LANES}
            snapshot_state = topology / "snapshot-state" / (name + ".json")
            observed_actions = {key: state[key] for key in (
                ("withdrawal",) if name == "withdrawn" else
                ("withdrawal", "reapproval", "damage_rescan") if name == "reapproved-rescanned" else
                ("withdrawal", "reapproval", "damage_rescan", "changed_evidence"))}
            write(snapshot_state, json.dumps({"queries": snapshot_queries, "operations": observed_actions}, indent=2, sort_keys=True) + "\n")
            snapshot_prompt = destination / "prompts" / (identifier + "--" + name + ".txt")
            write(snapshot_prompt, prompt(chunk, scenario, snapshot_child, fixture_flow(topology / "snapshot-bin" / name, snapshot_parent / "runtime-home"), selected_skill) + "\nFixture state: " + str(snapshot_state) + "\nThis is a fresh lane invocation for retained step " + name + ". Inspect the recorded operations and current evidence; explain whether approval, content repair, or evidence validity changed.\nUse query: shared ancestor archive")
            sub_attempts.append({"id": identifier + "--" + name, "fixture_root": str(snapshot_child), "prompt": str(snapshot_prompt), "prompt_sha256": sha(snapshot_prompt), "fixture_state": str(snapshot_state), "fixture_state_sha256": sha(snapshot_state), "runtime": runtime, "lane": lane})
        value["sub_attempts"] = sub_attempts
    return value


def prepare(destination):
    destination = destination.resolve()
    if destination.exists():
        raise ValueError("evaluation destination must be new; preserve prior evidence")
    destination.mkdir(parents=True)
    wrapper, sync = flow_wrapper(destination)
    cells = []
    for runtime in RUNTIMES:
        cells += [cell(destination, wrapper, 1, runtime, scenario, None) for scenario in CHUNK1]
        cells += [cell(destination, wrapper, 2, runtime, scenario, None) for scenario in CHUNK2]
        cells += [cell(destination, wrapper, 3, runtime, scenario, lane) for lane in LANES for scenario in CHUNK3]
    if len(cells) != 28 or len({item["id"] for item in cells}) != 28:
        raise AssertionError("must map one-to-one to 28 ledger cells")
    source_paths = sorted((REPO / "cli").glob("*.py")) + [Path(__file__), *[REPO / "scaffolds/default/commands" / ("flow-" + lane + ".md") for lane in LANES]]
    inventory = {"schema_version": 2, "prepared_at": datetime.now(timezone.utc).isoformat(),
                 "commit": run(["git", "rev-parse", "HEAD"], REPO, os.environ)["stdout"].strip(),
                 "source_sha256": {str(p.relative_to(REPO)): sha(p) for p in source_paths},
                 "client_versions": {runtime: run([runtime, "--version"], REPO, os.environ) for runtime in RUNTIMES},
                 "generated_sha256": {str(p.relative_to(destination)): sha(p) for p in (destination / "generated-home").rglob("SKILL.md")},
                 "authentication_context": "Providers use the operator's existing authenticated HOME; Flow commands use isolated fixture HOME. Credentials are not copied.",
                 "python": sys.version, "sync": sync, "cells": cells}
    path = destination / "inventory.json"
    write(path, json.dumps(inventory, indent=2, sort_keys=True) + "\n")
    return path


def invoke(item, destination):
    path = destination / "attempts" / (item["id"] + ".json")
    if path.exists():
        raise FileExistsError("attempt already exists; preserve it and use a new fixture version")
    text, cwd = Path(item["prompt"]).read_text(), Path(item["fixture_root"])
    authority_root = cwd.parent if cwd.name == "child" else cwd
    before = {str(p.relative_to(authority_root)): sha(p) for p in authority_root.rglob("*") if p.is_file() and ".flow" in p.relative_to(authority_root).parts and "runtime-home" not in p.relative_to(authority_root).parts}
    started_at = datetime.now(timezone.utc).isoformat()
    argv = (["claude", "--print", "--verbose", "--output-format", "stream-json", "--permission-mode", "dontAsk", "--allowedTools", "Read,Bash,Glob,Grep", "--", text]
            if item["runtime"] == "claude" else
            ["codex", "exec", "--json", "--sandbox", "workspace-write", "--skip-git-repo-check", "-C", str(cwd), text])
    outcome = run(argv, cwd, {**os.environ, "NO_COLOR": "1"}, timeout=180)
    after = {str(p.relative_to(authority_root)): sha(p) for p in authority_root.rglob("*") if p.is_file() and ".flow" in p.relative_to(authority_root).parts and "runtime-home" not in p.relative_to(authority_root).parts}
    outcome.update({"started_at": started_at, "completed_at": datetime.now(timezone.utc).isoformat(), "authority_before": before, "authority_after": after,
                    "status": "unavailable" if outcome["timed_out"] else "unreviewed_attempt", "prompt_sha256": item["prompt_sha256"], "fixture_state_sha256": item["fixture_state_sha256"]})
    write(path, json.dumps(outcome, indent=2, sort_keys=True) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--runtime", choices=RUNTIMES, help="execute one provider; all fixtures remain prepared")
    args = parser.parse_args()
    inventory = prepare(args.destination)
    if args.execute:
        items = [step for cell in json.loads(inventory.read_text())["cells"] if args.runtime is None or cell["runtime"] == args.runtime for step in cell.get("sub_attempts", [cell])]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {pool.submit(invoke, item, args.destination): item["id"] for item in items}
            for future in as_completed(futures):
                future.result()
                print("retained " + futures[future], flush=True)
    print(inventory)


if __name__ == "__main__":
    main()
