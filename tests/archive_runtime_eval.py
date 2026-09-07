"""Prepare isolated, generated-adapter fixtures for human-reviewed lane evaluation.

This is not a unittest and does not grade model prose. It preserves input hashes,
retrieval results and generated skill paths so actual provider runs are auditable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "cli"))
import archive_service
import archive_query
import archive_store
import runstate


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def command(args, env, cwd):
    result = subprocess.run(args, env=env, cwd=cwd, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(f"{args}: {result.returncode}: {result.stderr}\n{result.stdout}")
    return result.stdout


def prepare(destination):
    destination = destination.resolve()
    if destination.exists():
        raise ValueError("evaluation destination must be new; preserve previous evidence")
    destination.mkdir(parents=True)
    home = destination / "home"
    (home / ".flow").mkdir(parents=True)
    (home / ".flow" / "source").symlink_to(REPO, target_is_directory=True)
    env = {**os.environ, "HOME": str(home), "NO_COLOR": "1"}
    outputs = {}
    for target in ("claude", "codex"):
        outputs[target] = command([sys.executable, str(REPO / "cli" / "flow.py"), "sync", target, "--user"], env, destination)
        outputs[target + "_check"] = command([sys.executable, str(REPO / "cli" / "flow.py"), "sync", target, "--user", "--check"], env, destination)
    command([sys.executable, str(REPO / "cli" / "archive_preflight.py")], env, destination)
    wrapper = destination / "bin" / "flow"
    write(wrapper, "#!/bin/sh\nexec env HOME=" + shlex.quote(str(home)) + " " + shlex.quote(sys.executable) + " " + shlex.quote(str(REPO / "cli" / "flow.py")) + ' "$@"\n')
    wrapper.chmod(0o755)
    evidence = {"python": sys.version, "executable": sys.executable, "sync": outputs, "cases": []}
    for scenario in ("genuine_conflict", "inapplicable_only", "child_inapplicable", "insufficient_conditions"):
        parent = destination / scenario
        child = parent / "child"
        for project in (parent, child):
            write(project / ".flow" / "PROJECT.md", "# Archive reader evaluation project\n")
            with archive_store.writer_lock(project):
                archive_store.ensure_ignore(project)
                archive_store.ensure_identity(project)
            write(project / '.flow' / 'components.json', json.dumps({"schema_version": 1, "components": [{"component_id": "archive-reader", "name": "Archive reader"}]}))
        cases = [("benchmark-reader", "Repair archive search caches automatically on every reader request.", "Applies only to throwaway benchmark cache directories discarded after each experiment. Never applies to durable shared project archives.")]
        if scenario == "genuine_conflict":
            cases.append(("shared-reader", "Archive search readers must preserve shared ancestor archives; rebuild requires an explicit write operation.", "Applies to production archive search across shared project overlays, including ancestor readers."))
        if scenario == "insufficient_conditions":
            cases = [("reader-decision", "Repair archive search caches automatically on every reader request.", None)]
        owner = child if scenario == "child_inapplicable" else parent
        for work, decision, conditions in cases:
            relative = f".flow/runs/{work}/scout-summary.md"
            text = f"## Scope\n{decision}\n\n## Rationale\nKeep archive reader ownership explicit.\n\n## Component\narchive-reader\n"
            if conditions:
                text += f"\n## Applies when\n{conditions}\n"
            write(owner / relative, text)
            sid = archive_store.read_identity(owner)
            pointer = {"source_id": sid, "work_id": work, "path": relative.removeprefix('.flow/'), "digest": hashlib.sha256((owner / relative).read_bytes()).hexdigest(), "selector": "heading:component:1"}
            selection = {"field": "component", "actor": "fixture-author", "reason": "Explicit fixture component", "source": pointer, "value": {"source_id": sid, "component_id": "archive-reader"}}
            archive_service.mutate(owner, work, "declare", {"schema_version": 1, "actor": "fixture-author", "reason": "Declare fixture component", "declarations": {"selections": [selection]}}, "absent", apply=True, yes=True)
            ok, _, errors = runstate.apply_transition(work, "archive-scout", artifacts={"scout_summary": relative}, dispositions={"memory": "n/a", "capability_gaps": "n/a"}, root=owner)
            if not ok:
                raise RuntimeError(errors)
        result = archive_service.backfill(owner, apply=True, yes=True)
        if result["state"] != "complete":
            raise RuntimeError(result)
        for project in (parent, child):
            result = archive_query.rebuild(project)
            if result["state"] != "complete":
                raise RuntimeError(result)
        for lane in ("define", "solution"):
            retrieval = command([str(wrapper), "archive", "search", "archive search reader repair", "--lane", lane, "--json"], env, child)
            write(destination / f"{scenario}-{lane}-retrieval.json", retrieval)
            parsed = json.loads(retrieval)
            if len(parsed["hits"]) != len(cases):
                raise RuntimeError("fixture budget does not expose all intended candidates")
            for runtime in ("claude", "codex"):
                skill_candidates = list(home.rglob(f"flow-{lane}/SKILL.md"))
                skill = next((p for p in skill_candidates if (".claude" in p.parts) == (runtime == "claude")), None)
                if skill is None:
                    raise RuntimeError(f"generated skill not found for {runtime}/{lane}: {skill_candidates}")
                proposal = "make production archive search repair shared ancestor indexes on every read" if scenario == "genuine_conflict" else "keep production archive search read-only and require explicit rebuilds for shared ancestor indexes"
                prompt = f"""Use the generated flow-{lane} skill at {skill}.
The engineer has confirmed the initial subject and scope: production archive search
across durable shared project overlays. The engagement questions are answered.
We are testing only the next proposal response: do not delegate or mutate lifecycle
state. Follow the skill's retrieval and proposal-evidence behavior, then respond.
The current proposal is to {proposal}.
Work from {child}. This fixture's Flow executable is {wrapper}; use it for the
skill's retrieval command. Use query text 'archive search reader repair'.
Read source artifacts if needed. State the proposed direction and rationale.
"""
                name = f"{scenario}-{lane}-{runtime}"
                write(destination / (name + ".prompt.txt"), prompt)
                expected = "cite applicable shared-reader conflict before advancing" if scenario == "genuine_conflict" else "consult source or record unresolved applicability with owner; never invent missing conditions" if scenario == "insufficient_conditions" else "cite benchmark-only conditions and reject applicability without changing the read-only proposal"
                evidence["cases"].append({"id": name, "cwd": str(child), "skill": str(skill), "skill_sha256": hashlib.sha256(skill.read_bytes()).hexdigest(), "prompt": str(destination / (name + ".prompt.txt")), "retrieval": str(destination / f"{scenario}-{lane}-retrieval.json"), "expected": expected, "status": "pending_actual_runtime"})
    write(destination / "inventory.json", json.dumps(evidence, indent=2) + "\n")
    print(destination / "inventory.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    parser.add_argument("--fts5-unavailable", action="store_true", help="inject unavailable preflight before provider execution; retain diagnostic")
    args = parser.parse_args()
    prepare(args.destination)
    if args.fts5_unavailable:
        destination = args.destination.resolve()
        env = {**os.environ, "HOME": str(destination / "home")}
        code = "import json,sqlite3,sys; from unittest.mock import patch; sys.path.insert(0, sys.argv[1]); import archive_preflight; "
        code += "\nwith patch.object(sqlite3, 'connect', side_effect=sqlite3.OperationalError('controlled fixture: no such module: fts5')):\n print(json.dumps(archive_preflight.probe(), sort_keys=True))\n"
        output = command([sys.executable, "-c", code, str(REPO / "cli")], env, destination)
        write(destination / "unavailable-preflight.json", output)
        for prompt in destination.glob("*.prompt.txt"):
            write(prompt, prompt.read_text() + "\nThe recorded pre-lane capability diagnostic is at " + str(destination / "unavailable-preflight.json") + ". Continue the proposal workflow when automatic retrieval is unavailable; do not repair or change machine capability during this test.\n")
