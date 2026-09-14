"""CLI contracts for expertise feasibility and immutable fixture preparation."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from expertise_model import (
    DEFAULT_LIMITS, PLAUSIBLE_PATHS,
    PRIMARY_CLASSES,
    SCHEMA_VERSION,
    SPLITS,
    canonical_json,
    digest,
    normalized_task,
    task_identifiers,
    validate_outcome,
)
from expertise import canonical_snapshot
from expertise_admission import SimilarityStrategy, TriggerRuleStrategy
from expertise_projection import inspect as inspect_projection, projection_identity, publish as publish_projection
from expertise_receipts import (
    inspect_receipts, purge as purge_receipts, receipt_root, write_feedback,
    write_post, write_pre,
)
from expertise_runtime import (
    ExpertiseRuntimeError, data_root as expertise_data_root, install as install_runtime,
    provider as load_provider, status as runtime_status,
)
from expertise_service import ROLES, execute, load_fact_definitions
from expertise_service import (
    ADMISSION_INPUT_REVISION, DISPOSITION_CONTRACT_REVISION, ENVELOPE_REVISION,
    FACT_DERIVATION_REVISION, PACKING_REVISION,
)
from fsutil import repo_root
from paths import FLOW_HOME, SCAFFOLD_DIR, USER_OVERLAY_DIR
from expertise_campaign import repeatable, score_candidate, select_candidate


WORK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
EXPECTED_CLASSES = {
    "applicable": 10,
    "plausible-inapplicable": 10,
    "true-no-match": 6,
    "integrity": 4,
}
EVALUATION_V1_DIGESTS = {
    "manifest": "d2f42382c7c52bc51227596ceb37e58dc5a5f45e77b1edb026441270afa978b0",
    "results": "9101f9c2902ffb34b5077f19c126c736e37e6227896e9438a5b3b9e68d2dee57",
}
SIMILARITY_GRID = [0.55, 0.60, 0.65, 0.70, 0.75, 0.80]
FIXTURE_EXPECTED_KEYS = {
    "outer_state", "cause", "admission_state", "candidate_decision", "disposition",
}
FIXTURE_DECISIONS = {"admitted", "rejected", "controlled_delivery", "not_run"}
PROHIBITED_AFTER_PAUSE = [
    "fixture_authoring", "embedding", "ranking", "scoring", "selection",
    "release",
]
REQUIRED_ENVIRONMENTS = {
    "macos-26.6-arm64-python-3.12.13",
    "ubuntu-24.04-x64-python-3.10.21",
    "ubuntu-24.04-x64-python-3.11.16",
    "ubuntu-24.04-x64-python-3.12.14",
    "ubuntu-24.04-x64-python-3.13.15",
}
CAMPAIGN_SOURCE_FILES = (
    "cli/expertise_admission.py",
    "cli/expertise_campaign.py",
    "cli/expertise_commands.py",
    "cli/expertise_model.py",
    "cli/expertise_projection.py",
    "cli/expertise_ranker.py",
    "cli/expertise_service.py",
)


class ExpertiseCommandError(ValueError):
    pass


def register(sub) -> None:
    parser = sub.add_parser(
        "expertise",
        help="prepare, inspect, and evaluate local agent-expertise retrieval",
        description=(
            "Local expertise retrieval and admission. Feasibility and fixture "
            "commands create no model, vector, score, or automatic agent behavior."
        ),
    )
    actions = parser.add_subparsers(dest="expertise_action", required=True)
    feasibility = actions.add_parser(
        "feasibility",
        help="validate corpus, staffing, split-slot, and environment readiness before fixture work",
    )
    feasibility.add_argument("--run", required=True, dest="work_id")
    feasibility.add_argument("--plan", help="defaults to the run evidence feasibility-plan.json")
    feasibility.add_argument("--framework-dir", help=argparse.SUPPRESS)
    feasibility.add_argument("--json", action="store_true")

    fixtures = actions.add_parser("fixtures", help="validate frozen expertise evaluation fixture inputs")
    fixture_actions = fixtures.add_subparsers(dest="fixtures_action", required=True)
    validate = fixture_actions.add_parser("validate", help="validate one fixture manifest before scoring")
    validate.add_argument("--manifest", required=True)
    validate.add_argument("--framework-dir", help=argparse.SUPPRESS)
    validate.add_argument("--json", action="store_true")
    independence = fixture_actions.add_parser(
        "independence", help="find exact, identifier, and declared lexical overlap before held-out freeze"
    )
    independence.add_argument("--candidate", required=True)
    independence.add_argument("--against", required=True, help="comma-separated manifest paths")
    independence.add_argument("--threshold", type=float, default=0.8)
    independence.add_argument("--json", action="store_true")

    model = actions.add_parser("model", help="install or inspect the pinned local embedding runtime")
    model_actions = model.add_subparsers(dest="model_action", required=True)
    model_install = model_actions.add_parser("install", help="explicitly install verified local model artifacts")
    model_install.add_argument("--accept-license", action="store_true")
    model_install.add_argument("--wheel-dir", help=argparse.SUPPRESS)
    model_install.add_argument("--model-source", help=argparse.SUPPRESS)
    model_install.add_argument("--json", action="store_true")
    model_status = model_actions.add_parser("status", help="verify local model and runtime readiness")
    model_status.add_argument("--json", action="store_true")

    index = actions.add_parser("index", help="refresh or inspect the disposable vector projection")
    index_actions = index.add_subparsers(dest="index_action", required=True)
    refresh = index_actions.add_parser("refresh", help="rebuild vectors from the canonical expertise corpus")
    refresh.add_argument("--framework-dir", help=argparse.SUPPRESS)
    refresh.add_argument("--user-dir", help=argparse.SUPPRESS)
    refresh.add_argument("--json", action="store_true")
    index_status = index_actions.add_parser("inspect", help="verify projection identity and integrity")
    index_status.add_argument("--json", action="store_true")

    query = actions.add_parser("query", help="run an explicit local expertise query and write its pre-agent receipt")
    query.add_argument("--role", required=True, choices=ROLES)
    query.add_argument("--query-file", required=True, help="UTF-8 task file; query text is never stored in receipts")
    query.add_argument("--strategy", required=True, choices=("similarity", "trigger-rules"))
    query.add_argument("--threshold", type=float, default=0.7)
    query.add_argument("--framework-dir", help=argparse.SUPPRESS)
    query.add_argument("--user-dir", help=argparse.SUPPRESS)
    query.add_argument("--json", action="store_true")

    brief = actions.add_parser("brief", help="prepare one bounded advisory brief for a Flow role dispatch")
    brief.add_argument("--role", required=True, choices=ROLES)
    brief.add_argument("--task-stdin", action="store_true", required=True,
                       help="read at most 32768 UTF-8 task bytes from stdin without a query file")
    brief.add_argument("--json", action="store_true")

    disposition = actions.add_parser("disposition", help="validate a coordinator handback and write its linked receipt")
    disposition.add_argument("--request-id", required=True)
    handback_input = disposition.add_mutually_exclusive_group(required=True)
    handback_input.add_argument("--handback")
    handback_input.add_argument("--handback-stdin", action="store_true",
                                help="read at most 32768 UTF-8 JSON bytes from stdin without a handback file")
    disposition.add_argument("--json", action="store_true")

    feedback = actions.add_parser("feedback", help="record a redacted observation about one local query")
    feedback.add_argument("--request-id", help="linked pre-agent request; omit only when preparation failed before a receipt")
    feedback.add_argument("--role", choices=ROLES, help="required for a failure without a request ID")
    feedback.add_argument("--lane", required=True, choices=(
        "define", "solution", "plan", "implement", "review", "archive", "init-project", "scout", "resume",
    ))
    feedback.add_argument("--category", required=True, choices=("useful", "inapplicable", "miss", "failure"))
    feedback.add_argument("--entry-id")
    feedback.add_argument("--json", action="store_true")

    receipt_parser = actions.add_parser("receipts", help="inspect or purge private retrieval receipts")
    receipt_actions = receipt_parser.add_subparsers(dest="receipts_action", required=True)
    receipt_inspect = receipt_actions.add_parser("inspect", help="inspect redacted receipt metadata")
    receipt_inspect.add_argument("--json", action="store_true")
    receipt_purge = receipt_actions.add_parser("purge", help="delete receipts older than the retention window")
    receipt_purge.add_argument("--days", type=int, default=30)
    receipt_purge.add_argument("--json", action="store_true")

    campaign = actions.add_parser("campaign", help="freeze and verify immutable expertise evaluation campaigns")
    campaign_actions = campaign.add_subparsers(dest="campaign_action", required=True)
    freeze = campaign_actions.add_parser("freeze", help="freeze an independently reviewed manifest after explicit approval")
    freeze.add_argument("--run", required=True, dest="work_id")
    freeze.add_argument("--manifest", required=True)
    freeze.add_argument("--approved-digest", required=True)
    freeze.add_argument("--approved-by", required=True)
    freeze.add_argument(
        "--independence-review",
        help="required for evaluation-v2; reviewed split-independence receipt",
    )
    freeze.add_argument("--framework-dir", help=argparse.SUPPRESS)
    freeze.add_argument("--json", action="store_true")
    verify = campaign_actions.add_parser("verify-freeze", help="verify an immutable campaign freeze before scoring")
    verify.add_argument("--run", required=True, dest="work_id")
    verify.add_argument("--split", required=True, choices=SPLITS)
    verify.add_argument("--json", action="store_true")
    retrieve = campaign_actions.add_parser("retrieve-calibration", help="run the frozen preregistered calibration retrieval matrix")
    retrieve.add_argument("--run", required=True, dest="work_id")
    retrieve.add_argument("--json", action="store_true")
    finalize = campaign_actions.add_parser("finalize-calibration", help="apply the frozen selector to retained calibration results")
    finalize.add_argument("--run", required=True, dest="work_id")
    finalize.add_argument("--dispositions", help="optional reviewed disposition evidence keyed by fixture and candidate")
    finalize.add_argument("--json", action="store_true")
    held_out = campaign_actions.add_parser(
        "retrieve-heldout",
        help="run the selected frozen configuration twice on evaluation-v2",
    )
    held_out.add_argument("--run", required=True, dest="work_id")
    held_out.add_argument("--json", action="store_true")
    held_out_final = campaign_actions.add_parser(
        "finalize-heldout",
        help="apply held-out dispositions and record the frozen stop or qualification decision",
    )
    held_out_final.add_argument("--run", required=True, dest="work_id")
    held_out_final.add_argument("--dispositions")
    held_out_final.add_argument(
        "--environment-evidence",
        help="reviewed exact-runtime matrix required for qualification",
    )
    held_out_final.add_argument("--json", action="store_true")


def _read_object(path: Path, label: str, *, maximum_bytes: int = 4 * 1024 * 1024) -> dict:
    try:
        size = path.stat().st_size
        if size > maximum_bytes:
            raise ExpertiseCommandError(
                f"{label} exceeds the {maximum_bytes}-byte input limit: {path}"
            )
        value = json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise ExpertiseCommandError(f"{label} does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ExpertiseCommandError(f"{label} is invalid JSON at line {exc.lineno}, column {exc.colno}") from exc
    if not isinstance(value, dict):
        raise ExpertiseCommandError(f"{label} must be a JSON object")
    return value


def _contained_no_symlink(path: Path, root: Path) -> Path:
    lexical_root = root.absolute()
    root = lexical_root.resolve()
    path = path.absolute()
    if path.is_relative_to(lexical_root):
        path = root / path.relative_to(lexical_root)
    if not path.is_relative_to(root):
        raise ExpertiseCommandError(f"evidence path escapes run root: {path}")
    for part in [path, *path.parents]:
        if part == root:
            break
        if part.is_symlink():
            raise ExpertiseCommandError(f"symlinked evidence path is not allowed: {part}")
    if path.exists() and path.is_symlink():
        raise ExpertiseCommandError(f"symlinked evidence path is not allowed: {path}")
    if not path.resolve().is_relative_to(root):
        raise ExpertiseCommandError(f"resolved evidence path escapes run root: {path}")
    return path


def _write_private_evidence(path: Path, content: str, run_root: Path) -> None:
    path = _contained_no_symlink(path, run_root)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    _contained_no_symlink(path, run_root)
    fd, name = tempfile.mkstemp(prefix=".expertise-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(name, 0o600)
        _contained_no_symlink(path, run_root)
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _framework(root: Path, override: str | None) -> Path:
    if override:
        path = Path(override).expanduser().resolve()
    elif (root / "scaffolds" / "default" / "expertise").is_dir():
        path = root / "scaffolds" / "default"
    else:
        from paths import SCAFFOLD_DIR
        path = SCAFFOLD_DIR
    if not (path / "expertise").is_dir():
        raise ExpertiseCommandError(f"framework expertise directory is missing: {path / 'expertise'}")
    return path


def _corpus_inventory(framework: Path) -> dict:
    roles: dict[str, dict] = {}
    ids: set[str] = set()
    files = sorted((framework / "expertise").glob("*.jsonld"))
    for path in files:
        document = _read_object(path, f"corpus {path.name}")
        graph = document.get("@graph")
        if not isinstance(graph, list):
            raise ExpertiseCommandError(f"corpus {path.name} has no @graph array")
        role = path.stem
        role_ids: list[str] = []
        for index, raw in enumerate(graph):
            if not isinstance(raw, dict):
                raise ExpertiseCommandError(f"corpus {path.name} entry {index} is not an object")
            entry_id = raw.get("@id")
            if not isinstance(entry_id, str) or not entry_id:
                raise ExpertiseCommandError(f"corpus {path.name} entry {index} has no @id")
            audience = raw.get("audience", {})
            if not isinstance(audience, dict) or audience.get("audienceType") != role:
                raise ExpertiseCommandError(f"corpus {path.name} entry {entry_id} has the wrong role")
            if entry_id in ids:
                raise ExpertiseCommandError(f"duplicate expertise entry id: {entry_id}")
            ids.add(entry_id)
            role_ids.append(entry_id)
        raw_bytes = path.read_bytes()
        roles[role] = {
            "path": f"expertise/{path.name}",
            "entry_ids": role_ids,
            "entry_count": len(role_ids),
            "sha256": hashlib.sha256(raw_bytes).hexdigest(),
        }
    return {
        "roles": roles,
        "role_count": len(roles),
        "entry_count": len(ids),
        "entry_ids": sorted(ids),
        "digest": digest({role: {"entry_ids": item["entry_ids"], "sha256": item["sha256"]} for role, item in roles.items()}),
    }


def _validate_staffing(staffing: Any, problems: list[str]) -> dict:
    if not isinstance(staffing, dict):
        problems.append("staffing must be an object")
        return {}
    normalized: dict[str, dict] = {}
    all_identities: list[str] = []
    for split in SPLITS:
        item = staffing.get(split)
        if not isinstance(item, dict):
            problems.append(f"staffing.{split} is missing")
            continue
        groups: dict[str, list[str]] = {}
        for field, minimum in (("query_authors", 3), ("labelers", 1), ("freeze_reviewers", 1)):
            values = item.get(field)
            if not isinstance(values, list) or len(values) < minimum or any(
                not isinstance(value, str) or not value.strip() for value in values
            ):
                problems.append(f"staffing.{split}.{field} requires at least {minimum} named available identities")
                groups[field] = []
                continue
            if len(values) != len(set(values)):
                problems.append(f"staffing.{split}.{field} contains duplicate identities")
            groups[field] = values
        split_identities = [identity for values in groups.values() for identity in values]
        if len(split_identities) != len(set(split_identities)):
            problems.append(f"staffing.{split} author, labeler, and reviewer groups must be disjoint")
        all_identities.extend(split_identities)
        if item.get("status") != "available":
            problems.append(f"staffing.{split} must mark every assignment available")
        evidence = item.get("evidence")
        if not isinstance(evidence, str) or not evidence.strip():
            problems.append(f"staffing.{split} requires availability evidence")
        if split == "evaluation-v2" and item.get("calibration_score_access") is not False:
            problems.append("staffing.evaluation-v2 must attest calibration_score_access=false")
        normalized[split] = groups | {
            "status": item.get("status"),
            "evidence": evidence,
            "calibration_score_access": item.get("calibration_score_access"),
        }
    if len(all_identities) != len(set(all_identities)):
        problems.append("staffing identities must be distinct across both splits")
    return normalized


def _validate_slots(
    slots: Any, roles: set[str], entry_ids: set[str], staffing: dict, problems: list[str]
) -> dict:
    if not isinstance(slots, list):
        problems.append("slots must be a list")
        return {}
    seen: set[str] = set()
    by_split: dict[str, list[dict]] = defaultdict(list)
    for index, raw in enumerate(slots):
        if not isinstance(raw, dict):
            problems.append(f"slot {index} is not an object")
            continue
        slot_id = raw.get("id")
        split = raw.get("split")
        role = raw.get("role")
        primary = raw.get("primary_class")
        if not isinstance(slot_id, str) or not slot_id:
            problems.append(f"slot {index} has no id")
            continue
        if slot_id in seen:
            problems.append(f"duplicate slot id: {slot_id}")
        seen.add(slot_id)
        if split not in SPLITS:
            problems.append(f"slot {slot_id} has invalid split")
            continue
        if role not in roles:
            problems.append(f"slot {slot_id} names ineligible role {role}")
        if primary not in PRIMARY_CLASSES:
            problems.append(f"slot {slot_id} has invalid primary_class")
        target = raw.get("target_entry_id")
        if target is not None and target not in entry_ids:
            problems.append(f"slot {slot_id} names unknown target_entry_id {target}")
        if primary == "plausible-inapplicable" and raw.get("plausible_path") not in PLAUSIBLE_PATHS:
            problems.append(f"slot {slot_id} requires a plausible_path")
        slot_payload = {key: value for key, value in raw.items() if key != "task_slot_digest"}
        if raw.get("task_slot_digest") != digest(slot_payload):
            problems.append(f"slot {slot_id} task_slot_digest does not bind its metadata")
        split_staffing = staffing.get(split, {})
        assignment_fields = {
            "query_author": "query_authors",
            "labeler": "labelers",
            "reviewer": "freeze_reviewers",
        }
        assignment_values: list[str] = []
        for field, group in assignment_fields.items():
            identity = raw.get(field)
            assignment_values.append(identity)
            if identity not in split_staffing.get(group, []):
                problems.append(f"slot {slot_id} {field} is not in staffing.{split}.{group}")
        if len(set(assignment_values)) != 3:
            problems.append(f"slot {slot_id} query author, labeler, and reviewer must be distinct")
        by_split[split].append(raw)
    summary: dict[str, dict] = {}
    for split in SPLITS:
        rows = by_split.get(split, [])
        counts = Counter(row.get("primary_class") for row in rows)
        if len(rows) != 30:
            problems.append(f"{split} requires exactly 30 distinct slots, found {len(rows)}")
        for name, expected in EXPECTED_CLASSES.items():
            if counts.get(name, 0) != expected:
                problems.append(f"{split} requires {expected} {name} slots, found {counts.get(name, 0)}")
        role_counts = Counter(row.get("role") for row in rows)
        for role in sorted(roles):
            if role_counts.get(role, 0) < 2:
                problems.append(f"{split} requires at least two slots for role {role}")
        plausible = Counter(row.get("plausible_path") for row in rows if row.get("primary_class") == "plausible-inapplicable")
        for path in sorted(PLAUSIBLE_PATHS):
            if plausible.get(path, 0) != 5:
                problems.append(f"{split} requires five plausible {path} slots, found {plausible.get(path, 0)}")
        semantic = sum(bool(row.get("semantic_no_overlap")) and row.get("primary_class") == "applicable" for row in rows)
        if semantic < 3:
            problems.append(f"{split} requires at least three applicable semantic-no-overlap slots")
        semantic_authors = {
            row.get("query_author") for row in rows
            if row.get("primary_class") == "applicable" and row.get("semantic_no_overlap") is True
        }
        if len(semantic_authors) < 3:
            problems.append(f"{split} semantic-no-overlap slots require at least three independent authors")
        pairs: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            if isinstance(row.get("trigger_pair"), str) and row.get("trigger_pair"):
                pairs[row["trigger_pair"]].append(row)
        valid_pairs = [
            pair for pair in pairs.values()
            if len(pair) == 2
            and {x.get("primary_class") for x in pair} == {"applicable", "plausible-inapplicable"}
            and len({x.get("role") for x in pair}) == 1
            and all(x.get("one_fact_difference") is True for x in pair)
        ]
        pair_roles = {pair[0].get("role") for pair in valid_pairs}
        if len(valid_pairs) < 4 or "support-lead" not in pair_roles or len(pair_roles) < 2:
            problems.append(f"{split} requires four valid one-fact trigger pairs spanning support-lead and another role")
        summary[split] = {
            "total": len(rows),
            "primary_classes": dict(sorted(counts.items())),
            "role_counts": dict(sorted(role_counts.items())),
            "plausible_paths": dict(sorted(plausible.items())),
            "semantic_no_overlap_applicable": semantic,
            "valid_trigger_pairs": len(valid_pairs),
        }
    if len(seen) != 60:
        problems.append(f"the campaign requires 60 globally distinct slot ids, found {len(seen)}")
    return summary


def assess_feasibility(plan: dict, corpus: dict) -> dict:
    problems: list[str] = []
    if plan.get("schema_version") != SCHEMA_VERSION:
        problems.append("unsupported feasibility plan schema_version")
    staffing = _validate_staffing(plan.get("staffing"), problems)
    slots = _validate_slots(
        plan.get("slots"), set(corpus["roles"]), set(corpus["entry_ids"]), staffing, problems
    )
    environments = plan.get("environments")
    if not isinstance(environments, list):
        problems.append("environments must be a list")
        environment_summary = {}
    else:
        environment_summary = {}
        for item in environments:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                problems.append("every environment must be an object with an id")
                continue
            environment_id = item["id"]
            if environment_id in environment_summary:
                problems.append(f"duplicate environment: {environment_id}")
            environment_summary[environment_id] = item
            if item.get("status") != "available":
                problems.append(f"required environment is not available: {environment_id}")
            for field in ("runner", "validation_command", "availability_evidence"):
                if not isinstance(item.get(field), str) or not item[field].strip():
                    problems.append(f"environment {environment_id} requires {field}")
        extras = set(environment_summary) - REQUIRED_ENVIRONMENTS
        if extras:
            problems.append(f"unexpected environments: {', '.join(sorted(extras))}")
        for environment in sorted(REQUIRED_ENVIRONMENTS):
            if environment not in environment_summary:
                problems.append(f"required environment is not available: {environment}")
    state = "feasible" if not problems else "paused_for_engineer_decision"
    assignment_digest = digest(staffing)
    gap = "; ".join(problems)
    return {
        "schema_version": SCHEMA_VERSION,
        "state": state,
        "reason": None if not problems else _pause_reason(problems),
        "blocking_checks": problems,
        "prohibited_next_actions": [] if not problems else PROHIBITED_AFTER_PAUSE,
        "automatic_retrieval": "disabled",
        "gap": gap or None,
        "remedies": [] if not problems else [
            "correct the feasibility plan and rerun before fixture authoring or scoring"
        ],
        "corpus_digest": corpus["digest"],
        "assignment_digest": assignment_digest,
        "distinct_task_slots": sum(item.get("total", 0) for item in slots.values()),
        "eligible_roles": sorted(corpus["roles"]),
        "assignments": staffing,
        "corpus": corpus,
        "staffing": staffing,
        "slots": slots,
        "environments": [environment_summary[key] for key in sorted(environment_summary)],
        "plan_digest": digest(plan),
    }


def _pause_reason(problems: list[str]) -> str:
    if any("staffing" in item or "author" in item or "reviewer" in item for item in problems):
        return "staffing_gap"
    if any("environment" in item for item in problems):
        return "environment_gap"
    return "corpus_gap"


def _decision_markdown(result: dict) -> str:
    lines = [
        "# Expertise retrieval feasibility decision",
        "",
        f"- State: `{result['state']}`",
        f"- Automatic retrieval: `{result['automatic_retrieval']}`",
        f"- Plan digest: `{result['plan_digest']}`",
        f"- Corpus digest: `{result['corpus_digest']}`",
        f"- Assignment digest: `{result['assignment_digest']}`",
    ]
    if result["blocking_checks"]:
        lines.extend(["", "## Blocking checks", ""])
        lines.extend(f"- {item}" for item in result["blocking_checks"])
        lines.extend(["", "## Prohibited next actions", ""])
        lines.extend(f"- `{item}`" for item in result["prohibited_next_actions"])
        lines.extend(["", "Return to the engineer to revise corpus, staffing, or environments, or stop the campaign."])
    else:
        lines.extend(["", "The pre-fixture corpus, staffing, slot, and environment checks pass. Fixture authoring may begin; scoring remains locked until the applicable engineer-approved freeze."])
    return "\n".join(lines) + "\n"


def feasibility_command(args) -> int:
    root = repo_root()
    if not WORK_ID_RE.fullmatch(args.work_id):
        return _emit({"state": "invalid_request", "reason": "invalid work id"}, args.json, 2)
    run = root / ".flow" / "runs" / args.work_id
    try:
        if not run.is_dir():
            raise ExpertiseCommandError(f"run does not exist: {args.work_id}")
        plan_path = Path(args.plan).expanduser().resolve() if args.plan else run / "evidence" / "feasibility-plan.json"
        plan = _read_object(plan_path, "feasibility plan")
        result = assess_feasibility(plan, _corpus_inventory(_framework(root, args.framework_dir)))
        result["work_id"] = args.work_id
        result["observed_at"] = datetime.now(timezone.utc).isoformat()
        evidence = run / "evidence"
        _write_private_evidence(
            evidence / "feasibility-v1.json",
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            run,
        )
        _write_private_evidence(
            evidence / "feasibility-decision.md", _decision_markdown(result), run
        )
        return _emit(result, args.json, 0 if result["state"] == "feasible" else 3)
    except (OSError, ExpertiseCommandError, ValueError, TypeError) as exc:
        return _emit({"state": "invalid_request", "reason": str(exc)}, args.json, 2)


def _fixture_rows(manifest: dict) -> list[dict]:
    fixtures = manifest.get("fixtures")
    if not isinstance(fixtures, list):
        raise ExpertiseCommandError("fixture manifest fixtures must be a list")
    return fixtures


def validate_fixture_manifest(manifest: dict, corpus: dict | None = None) -> dict:
    problems: list[str] = []
    split = manifest.get("split")
    expected_top_level = {
        "schema_version", "split", "status", "scoring_state", "freeze_authorization",
        "evaluation_v1_digests", "candidate_rule_family", "preregistered_similarity_grid",
        "eligible_roles", "fixtures", "trigger_pairs", "provenance",
    }
    if split == "evaluation-v2":
        expected_top_level |= {
            "selected_candidate_id", "selected_configuration_digest",
            "calibration_score_access",
        }
    extra_top_level = set(manifest) - expected_top_level
    missing_top_level = expected_top_level - set(manifest)
    if extra_top_level:
        problems.append(f"fixture manifest has unexpected fields: {', '.join(sorted(extra_top_level))}")
    if missing_top_level:
        problems.append(f"fixture manifest is missing fields: {', '.join(sorted(missing_top_level))}")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        problems.append("unsupported fixture manifest schema_version")
    if split not in SPLITS:
        problems.append("fixture manifest split must be calibration-v1 or evaluation-v2")
    if split == "evaluation-v2":
        if manifest.get("calibration_score_access") is not False:
            problems.append("evaluation-v2 must attest calibration_score_access=false")
        if not isinstance(manifest.get("selected_candidate_id"), str) or not manifest["selected_candidate_id"]:
            problems.append("evaluation-v2 requires the selected calibration candidate id")
        if not re.fullmatch(r"[0-9a-f]{64}", str(manifest.get("selected_configuration_digest", ""))):
            problems.append("evaluation-v2 requires the selected executable configuration digest")
    if manifest.get("status") != "candidate_unfrozen":
        problems.append("fixture candidate must remain candidate_unfrozen before the approved freeze")
    if manifest.get("scoring_state") != "not_started":
        problems.append("fixture candidate must remain unscored before the approved freeze")
    freeze_authorization = manifest.get("freeze_authorization")
    if not isinstance(freeze_authorization, str) or not freeze_authorization.startswith("pending_"):
        problems.append("fixture candidate requires pending freeze authorization")
    if manifest.get("evaluation_v1_digests") != EVALUATION_V1_DIGESTS:
        problems.append("fixture manifest does not retain the immutable evaluation-v1 digests")
    if manifest.get("candidate_rule_family") != ["calibrated_similarity", "deterministic_trigger_rules"]:
        problems.append("fixture manifest must declare exactly the approved candidate rule family")
    if manifest.get("preregistered_similarity_grid") != SIMILARITY_GRID:
        problems.append("fixture manifest must declare exactly the preregistered similarity grid")
    try:
        rows = _fixture_rows(manifest)
    except ExpertiseCommandError as exc:
        return {"state": "invalid", "problems": [str(exc)], "manifest_digest": digest(manifest)}
    ids: set[str] = set()
    counts: Counter = Counter()
    roles: Counter = Counter()
    plausible: Counter = Counter()
    pairs: dict[str, list[dict]] = defaultdict(list)
    allowed_ids = set(corpus["entry_ids"]) if corpus else None
    allowed_roles = set(corpus["roles"]) if corpus else set(ROLES)
    eligible_roles = manifest.get("eligible_roles")
    if not isinstance(eligible_roles, list) or len(eligible_roles) != len(set(eligible_roles)):
        problems.append("eligible_roles must be a distinct list")
    elif set(eligible_roles) != allowed_roles:
        problems.append("eligible_roles must equal the canonical corpus roles")
    provenance = manifest.get("provenance")
    if not isinstance(provenance, dict):
        problems.append("fixture manifest provenance must be an object")
    else:
        for field in ("feasibility_plan_digest", "review_revisions_digest"):
            if not re.fullmatch(r"[0-9a-f]{64}", str(provenance.get(field, ""))):
                problems.append(f"fixture manifest provenance requires lowercase SHA-256 {field}")
        drafts = provenance.get("draft_sha256")
        if not isinstance(drafts, dict) or not drafts:
            problems.append("fixture manifest provenance requires draft_sha256")
        elif any(not isinstance(name, str) or not re.fullmatch(r"[0-9a-f]{64}", str(value)) for name, value in drafts.items()):
            problems.append("fixture manifest draft_sha256 values must be lowercase SHA-256")
    for index, raw in enumerate(rows):
        if not isinstance(raw, dict):
            problems.append(f"fixture {index} is not an object")
            continue
        fixture_id = raw.get("id")
        if not isinstance(fixture_id, str) or not fixture_id:
            problems.append(f"fixture {index} has no id")
            continue
        if fixture_id in ids:
            problems.append(f"duplicate fixture id: {fixture_id}")
        ids.add(fixture_id)
        primary = raw.get("primary_class")
        role = raw.get("role")
        counts[primary] += 1
        roles[role] += 1
        task = raw.get("task")
        if not isinstance(task, str) or not task.strip():
            problems.append(f"fixture {fixture_id} has no task text")
        if primary not in PRIMARY_CLASSES:
            problems.append(f"fixture {fixture_id} has invalid primary_class")
        if primary == "plausible-inapplicable":
            path = raw.get("plausible_path")
            plausible[path] += 1
            if path not in PLAUSIBLE_PATHS:
                problems.append(f"fixture {fixture_id} has invalid plausible_path")
        acceptable = raw.get("acceptable_entry_ids", [])
        prohibited = raw.get("prohibited_entry_ids", [])
        if (
            not isinstance(acceptable, list) or not isinstance(prohibited, list)
            or len(acceptable) != len(set(acceptable)) or len(prohibited) != len(set(prohibited))
            or any(not isinstance(value, str) or not value for value in acceptable + prohibited)
        ):
            problems.append(f"fixture {fixture_id} entry id sets must be lists")
        elif set(acceptable) & set(prohibited):
            problems.append(f"fixture {fixture_id} acceptable and prohibited entry ids overlap")
        elif allowed_ids is not None:
            for entry_id in acceptable + prohibited:
                if entry_id not in allowed_ids:
                    problems.append(f"fixture {fixture_id} names unknown entry id {entry_id}")
        for field in ("query_author", "labeler", "reviewer"):
            if not isinstance(raw.get(field), str) or not raw.get(field).strip():
                problems.append(f"fixture {fixture_id} requires {field}")
        identities = [raw.get("query_author"), raw.get("labeler"), raw.get("reviewer")]
        if len(set(identities)) != 3:
            problems.append(f"fixture {fixture_id} query author, labeler, and reviewer must differ")

        identifiers = raw.get("identifiers")
        if not isinstance(identifiers, list) or len(identifiers) != len(set(identifiers)) or any(
            not isinstance(value, str) or not value.strip() for value in identifiers
        ):
            problems.append(f"fixture {fixture_id} identifiers must be a distinct string list")
        elif isinstance(task, str):
            normalized = normalized_task(task)
            for identifier in identifiers:
                if normalized_task(identifier) not in normalized:
                    problems.append(f"fixture {fixture_id} identifier is absent from task: {identifier}")

        trigger = raw.get("trigger_fact")
        if not isinstance(trigger, dict) or set(trigger) != {"code", "value", "evidence_span"}:
            problems.append(f"fixture {fixture_id} trigger_fact must contain code, value, and evidence_span")
        else:
            code = trigger.get("code")
            if not isinstance(code, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", code):
                problems.append(f"fixture {fixture_id} has invalid trigger fact code")
            if trigger.get("value") not in {"present", "absent"}:
                problems.append(f"fixture {fixture_id} has invalid trigger fact value")
            span = trigger.get("evidence_span")
            if not isinstance(span, dict) or set(span) != {"start", "end", "text"}:
                problems.append(f"fixture {fixture_id} has invalid trigger evidence span")
            elif isinstance(task, str):
                start, end, text = span.get("start"), span.get("end"), span.get("text")
                if not (
                    isinstance(start, int) and not isinstance(start, bool)
                    and isinstance(end, int) and not isinstance(end, bool)
                    and isinstance(text, str) and 0 <= start < end <= len(task)
                    and task[start:end] == text
                ):
                    problems.append(f"fixture {fixture_id} trigger evidence span does not bind exact task text")

        oracle = raw.get("behavior_oracle")
        if not isinstance(oracle, dict) or set(oracle) != {"must_include", "must_avoid"}:
            problems.append(f"fixture {fixture_id} behavior_oracle must contain must_include and must_avoid")
        else:
            for field in ("must_include", "must_avoid"):
                values = oracle.get(field)
                if not isinstance(values, list) or not values or any(not isinstance(value, str) or not value.strip() for value in values):
                    problems.append(f"fixture {fixture_id} behavior_oracle.{field} must be a non-empty string list")

        expected = raw.get("expected")
        if not isinstance(expected, dict) or set(expected) != FIXTURE_EXPECTED_KEYS:
            problems.append(f"fixture {fixture_id} expected result has the wrong fields")
        else:
            expected_tuple = (
                expected.get("outer_state"), expected.get("cause"),
                expected.get("admission_state"), expected.get("candidate_decision"),
                expected.get("disposition"),
            )
            if expected.get("candidate_decision") not in FIXTURE_DECISIONS:
                problems.append(f"fixture {fixture_id} has invalid candidate_decision")
            if primary == "applicable" and expected_tuple != (
                "admitted", "candidates_delivered", "admitted", "admitted", "applied",
            ):
                problems.append(f"fixture {fixture_id} applicable expected result is inconsistent")
            elif primary == "plausible-inapplicable" and raw.get("plausible_path") == "admission-rejected" and expected_tuple != (
                "no_match", "no_candidate_admitted", "no_candidate_admitted", "rejected", None,
            ):
                problems.append(f"fixture {fixture_id} admission-rejected expected result is inconsistent")
            elif primary == "plausible-inapplicable" and raw.get("plausible_path") == "controlled-delivery" and expected_tuple not in {
                ("admitted", "candidates_delivered", "admitted", "controlled_delivery", "ignored"),
                ("admitted", "candidates_delivered", "admitted", "controlled_delivery", "insufficient_context"),
            }:
                problems.append(f"fixture {fixture_id} controlled-delivery expected result is inconsistent")
            elif primary == "true-no-match" and expected_tuple != (
                "no_match", "no_candidate_admitted", "no_candidate_admitted", "rejected", None,
            ):
                problems.append(f"fixture {fixture_id} true-no-match expected result is inconsistent")

        mutation = raw.get("integrity_mutation")
        assertions = raw.get("stage_assertions")
        if primary == "integrity":
            if not isinstance(mutation, dict) or mutation.get("entry_id") not in prohibited:
                problems.append(f"fixture {fixture_id} integrity mutation must target a prohibited entry")
            if not isinstance(assertions, dict) or set(assertions) != {"eligibility_state", "ranking_state"}:
                problems.append(f"fixture {fixture_id} integrity stage_assertions are required")
            if isinstance(mutation, dict) and isinstance(expected, dict) and set(expected) == FIXTURE_EXPECTED_KEYS:
                kind = mutation.get("kind")
                expected_tuple = (
                    expected.get("outer_state"), expected.get("cause"), expected.get("admission_state"),
                    expected.get("candidate_decision"), expected.get("disposition"),
                )
                if kind == "invalid_graph":
                    if set(mutation) != {"entry_id", "kind", "mutation", "expected_eligibility"} or mutation.get("mutation") != "duplicate_entry_id":
                        problems.append(f"fixture {fixture_id} invalid_graph mutation is not the approved duplicate-entry form")
                    if expected_tuple != ("invalid_corpus", "invalid_canonical_corpus", "not_run", "not_run", None):
                        problems.append(f"fixture {fixture_id} invalid-graph expected result is inconsistent; integrity expected result is inconsistent")
                    if acceptable:
                        problems.append(f"fixture {fixture_id} invalid-graph fixture cannot name an acceptable entry")
                elif kind in {"lifecycle_not_current", "lifecycle_withdrawn", "role_mismatch"}:
                    if set(mutation) != {"entry_id", "kind", "expected_eligibility"}:
                        problems.append(f"fixture {fixture_id} eligibility mutation has unexpected fields")
                    if mutation.get("expected_eligibility") != "excluded_before_ranking":
                        problems.append(f"fixture {fixture_id} eligibility mutation must require exclusion before ranking")
                    if expected_tuple != ("admitted", "candidates_delivered", "admitted", "admitted", "applied"):
                        problems.append(f"fixture {fixture_id} eligibility-mutation expected result is inconsistent; integrity expected result is inconsistent")
                    if not acceptable:
                        problems.append(f"fixture {fixture_id} eligibility mutation requires an alternate acceptable entry")
                else:
                    problems.append(f"fixture {fixture_id} has unsupported integrity mutation kind")
        elif mutation is not None or assertions is not None:
            problems.append(f"fixture {fixture_id} non-integrity fixture cannot declare an integrity mutation")
        pair = raw.get("trigger_pair")
        if isinstance(pair, str) and pair:
            pairs[pair].append(raw)
    if len(rows) != 30 or len(ids) != 30:
        problems.append(f"fixture manifest requires exactly 30 distinct fixtures, found {len(rows)} rows and {len(ids)} ids")
    for name, expected in EXPECTED_CLASSES.items():
        if counts.get(name, 0) != expected:
            problems.append(f"fixture manifest requires {expected} {name}, found {counts.get(name, 0)}")
    for role, count in roles.items():
        if role is None:
            problems.append("fixture role is missing")
    if corpus:
        for role in corpus["roles"]:
            if roles.get(role, 0) < 2:
                problems.append(f"fixture manifest requires at least two fixtures for role {role}")
    for path in PLAUSIBLE_PATHS:
        if plausible.get(path, 0) != 5:
            problems.append(f"fixture manifest requires five plausible {path}, found {plausible.get(path, 0)}")
    semantic = sum(isinstance(row, dict) and row.get("primary_class") == "applicable" and row.get("semantic_no_overlap") is True for row in rows)
    if semantic < 3:
        problems.append("fixture manifest requires three applicable semantic-no-overlap fixtures")
    declared_pairs = manifest.get("trigger_pairs")
    if not isinstance(declared_pairs, list):
        problems.append("trigger_pairs must be a list")
        declared_pairs = []
    declared_by_id: dict[str, dict] = {}
    for index, pair in enumerate(declared_pairs):
        if not isinstance(pair, dict):
            problems.append(f"trigger pair {index} is not an object")
            continue
        pair_id = pair.get("id")
        if not isinstance(pair_id, str) or not pair_id or pair_id in declared_by_id:
            problems.append(f"trigger pair {index} has an invalid or duplicate id")
            continue
        declared_by_id[pair_id] = pair
        pair_rows = pairs.get(pair_id, [])
        by_id = {row.get("id"): row for row in pair_rows}
        applicable_id, plausible_id = pair.get("applicable_id"), pair.get("plausible_id")
        discriminating = pair.get("discriminating_fact")
        if (
            set(pair) != {"id", "applicable_id", "plausible_id", "roles", "one_fact_difference", "shared_facts", "discriminating_fact"}
            or pair.get("one_fact_difference") is not True
            or len(pair_rows) != 2
            or applicable_id not in by_id or plausible_id not in by_id
            or by_id.get(applicable_id, {}).get("primary_class") != "applicable"
            or by_id.get(plausible_id, {}).get("primary_class") != "plausible-inapplicable"
        ):
            problems.append(f"trigger pair {pair_id} does not bind one applicable and one plausible fixture")
            continue
        pair_roles_value = pair.get("roles")
        actual_role = by_id[applicable_id].get("role")
        if pair_roles_value != [actual_role] or by_id[plausible_id].get("role") != actual_role:
            problems.append(f"trigger pair {pair_id} role binding is inconsistent")
        if not isinstance(pair.get("shared_facts"), list) or not pair["shared_facts"] or any(
            not isinstance(value, str) or not value.strip() for value in pair["shared_facts"]
        ):
            problems.append(f"trigger pair {pair_id} shared_facts must be a non-empty string list")
        if not isinstance(discriminating, dict) or set(discriminating) != {"code", "applicable_value", "plausible_value"}:
            problems.append(f"trigger pair {pair_id} discriminating_fact is invalid")
        else:
            left_code = by_id[applicable_id].get("trigger_fact", {}).get("code")
            right_code = by_id[plausible_id].get("trigger_fact", {}).get("code")
            if discriminating.get("code") != left_code or left_code != right_code:
                problems.append(f"trigger pair {pair_id} discriminating fact code does not match its fixtures")
            left_value = by_id[applicable_id].get("trigger_fact", {}).get("value")
            right_value = by_id[plausible_id].get("trigger_fact", {}).get("value")
            declared_left = discriminating.get("applicable_value")
            declared_right = discriminating.get("plausible_value")
            if not isinstance(declared_left, str) or declared_left.split(":", 1)[0] != left_value:
                problems.append(f"trigger pair {pair_id} applicable value does not match; discriminating fact values do not match its fixtures")
            if not isinstance(declared_right, str) or declared_right.split(":", 1)[0] != right_value:
                problems.append(f"trigger pair {pair_id} plausible value does not match; discriminating fact values do not match its fixtures")
    if set(pairs) != set(declared_by_id):
        problems.append("trigger_pair fixture references must exactly match the declared trigger_pairs")

    valid_pairs = [
        pair for pair in pairs.values()
        if len(pair) == 2
        and {x.get("primary_class") for x in pair} == {"applicable", "plausible-inapplicable"}
        and len({x.get("role") for x in pair}) == 1
        and all(x.get("one_fact_difference") is True for x in pair)
    ]
    pair_roles = {pair[0].get("role") for pair in valid_pairs}
    if len(valid_pairs) < 4 or "support-lead" not in pair_roles or len(pair_roles) < 2:
        problems.append("fixture manifest requires four valid trigger pairs spanning support-lead and another role")
    return {
        "state": "valid" if not problems else "invalid",
        "split": split,
        "fixture_count": len(rows),
        "primary_classes": dict(sorted((str(k), v) for k, v in counts.items())),
        "role_counts": dict(sorted((str(k), v) for k, v in roles.items())),
        "plausible_paths": dict(sorted((str(k), v) for k, v in plausible.items())),
        "semantic_no_overlap_applicable": semantic,
        "valid_trigger_pairs": len(valid_pairs),
        "problems": problems,
        "manifest_digest": digest(manifest),
    }


def fixture_validate_command(args) -> int:
    try:
        manifest = _read_object(Path(args.manifest), "fixture manifest")
        result = validate_fixture_manifest(manifest, _corpus_inventory(_framework(repo_root(), args.framework_dir)))
        return _emit(result, args.json, 0 if result["state"] == "valid" else 2)
    except (OSError, ExpertiseCommandError, ValueError, TypeError) as exc:
        return _emit({"state": "invalid_request", "reason": str(exc)}, args.json, 2)


def _terms(text: str) -> set[str]:
    return set(re.findall(r"[\w][\w_.:-]*", normalized_task(text)))


def independence(candidate: dict, references: list[dict], threshold: float) -> dict:
    if not 0.0 <= threshold <= 1.0:
        raise ExpertiseCommandError("threshold must be between 0 and 1")
    candidate_rows = _fixture_rows(candidate)
    reference_rows = [(manifest.get("split"), row) for manifest in references for row in _fixture_rows(manifest)]
    flags: list[dict] = []
    comparisons = 0
    for left in candidate_rows:
        if not isinstance(left, dict) or not isinstance(left.get("task"), str):
            continue
        left_text = normalized_task(left["task"])
        left_terms = _terms(left_text)
        declared_left = left.get("identifiers", [])
        left_ids = {
            normalized_task(value) for value in declared_left if isinstance(value, str) and value.strip()
        }
        for split, right in reference_rows:
            if not isinstance(right, dict) or not isinstance(right.get("task"), str):
                continue
            comparisons += 1
            right_text = normalized_task(right["task"])
            right_terms = _terms(right_text)
            union = left_terms | right_terms
            lexical = len(left_terms & right_terms) / len(union) if union else 1.0
            kinds = []
            if left_text == right_text:
                kinds.append("exact")
            declared_right = right.get("identifiers", [])
            right_ids = {
                normalized_task(value) for value in declared_right if isinstance(value, str) and value.strip()
            }
            shared_ids = sorted(left_ids & right_ids)
            if shared_ids:
                kinds.append("identifier")
            if lexical >= threshold:
                kinds.append("lexical")
            if kinds:
                flags.append({
                    "candidate_id": left.get("id"),
                    "reference_split": split,
                    "reference_id": right.get("id"),
                    "kinds": kinds,
                    "lexical_similarity": round(lexical, 6),
                    "shared_identifiers": shared_ids,
                    "candidate_task_digest": hashlib.sha256(left_text.encode()).hexdigest(),
                    "reference_task_digest": hashlib.sha256(right_text.encode()).hexdigest(),
                    "review_disposition": "pending",
                })
    return {
        "state": "review_required" if flags else "independent",
        "normalizer_revision": "nfkc-casefold-whitespace-v1",
        "task_field": "fixtures[].task",
        "identifier_method": "declared-fixture-identifiers-v1",
        "lexical_method": "token-set-jaccard-v1",
        "lexical_threshold": threshold,
        "comparisons": comparisons,
        "flags": flags,
        "candidate_manifest_digest": digest(candidate),
        "reference_manifest_digests": [digest(item) for item in references],
    }


def fixture_independence_command(args) -> int:
    try:
        candidate = _read_object(Path(args.candidate), "candidate fixture manifest")
        references = [_read_object(Path(raw), "reference fixture manifest") for raw in args.against.split(",") if raw]
        if not references:
            raise ExpertiseCommandError("--against requires at least one manifest")
        result = independence(candidate, references, args.threshold)
        return _emit(result, args.json, 0)
    except (OSError, ExpertiseCommandError, ValueError, TypeError) as exc:
        return _emit({"state": "invalid_request", "reason": str(exc)}, args.json, 2)


def _runtime_paths(args) -> tuple[Path, Path | None]:
    framework = _framework(repo_root(), getattr(args, "framework_dir", None))
    override = getattr(args, "user_dir", None)
    user = Path(override).expanduser().resolve() if override else USER_OVERLAY_DIR
    return framework, user if (user / "expertise").is_dir() else None


def model_command(args) -> int:
    if args.model_action == "status":
        result = runtime_status(FLOW_HOME)
        return _emit(result, args.json, 0 if result["state"] == "ready" else 1)
    try:
        result = install_runtime(
            FLOW_HOME,
            accept_license=args.accept_license,
            wheel_dir=Path(args.wheel_dir).expanduser().resolve() if args.wheel_dir else None,
            model_source=Path(args.model_source).expanduser().resolve() if args.model_source else None,
        )
        return _emit(result, args.json, 0)
    except ExpertiseRuntimeError as error:
        return _emit({"state": "unavailable", "reason": error.reason, "remedy": error.remedy}, args.json, 2)
    except (OSError, subprocess.SubprocessError) as error:
        return _emit({"state": "unavailable", "reason": "runtime_install_failed", "remedy": "retry with a supported Python interpreter"}, args.json, 2)


def index_command(args) -> int:
    if args.index_action == "inspect":
        readiness = runtime_status(FLOW_HOME)
        if readiness["state"] != "ready":
            return _emit(readiness, args.json, 1)
        try:
            framework, user = _runtime_paths(args)
            local_provider = load_provider(FLOW_HOME)
            snapshot = canonical_snapshot(ROLES, framework, user)
            expected = projection_identity(snapshot, local_provider)["digest"]
            result = inspect_projection(FLOW_HOME, expected)
        except (OSError, ValueError, TypeError, ExpertiseRuntimeError) as error:
            return _emit({"state": "unavailable", "reason": getattr(error, "reason", type(error).__name__)}, args.json, 2)
        return _emit(result, args.json, 0 if result["state"] == "ready" else 1)
    readiness = runtime_status(FLOW_HOME)
    if readiness["state"] != "ready":
        return _emit(readiness, args.json, 1)
    try:
        framework, user = _runtime_paths(args)
        local_provider = load_provider(FLOW_HOME)
        snapshot = canonical_snapshot(ROLES, framework, user)
        result = publish_projection(
            FLOW_HOME,
            snapshot,
            local_provider,
            verify_snapshot=lambda: canonical_snapshot(ROLES, framework, user)["corpus_digest"],
        )
        return _emit(result, args.json, 0)
    except (OSError, ValueError, TypeError, ExpertiseRuntimeError) as error:
        reason = getattr(error, "reason", type(error).__name__)
        return _emit({"state": "unavailable", "reason": reason, "remedy": "fix the canonical corpus or rerun the explicit model install"}, args.json, 2)


def _load_rules() -> tuple[dict[str, dict], dict]:
    document = _read_object(expertise_data_root() / "trigger-rules.json", "trigger rules")
    rows = document.get("rules")
    if not isinstance(rows, list):
        raise ExpertiseCommandError("trigger rules must contain a rules list")
    rules = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("entry_id"), str) or row["entry_id"] in rules:
            raise ExpertiseCommandError("trigger rules contain an invalid or duplicate entry")
        rules[row["entry_id"]] = row
    return rules, {"revision": document.get("revision"), "corpus_digest": document.get("corpus_digest")}


def _query_result(args, task_override: str | None = None) -> dict:
    if task_override is None:
        query_path = Path(args.query_file).expanduser().resolve()
        if query_path.stat().st_size > 32768:
            raise ExpertiseCommandError("query file exceeds 32768 UTF-8 bytes")
        task = query_path.read_text()
    else:
        task = task_override
    framework, user = _runtime_paths(args)
    readiness = runtime_status(FLOW_HOME)
    if readiness["state"] == "ready":
        local_provider = load_provider(FLOW_HOME)
    else:
        model = _read_object(expertise_data_root() / "model-manifest.json", "model manifest")

        class UnavailableProvider:
            provider_revision = model.get("provider", {}).get("revision", "unavailable-provider")
            model_artifact_digest = digest(model.get("model", {}))
            runtime_revision = f"unavailable:{readiness.get('environment_id', 'unknown')}"

            def embed(self, texts):
                from expertise_ranker import ExpertiseProviderError
                raise ExpertiseProviderError(readiness.get("reason", "provider_missing"))

        local_provider = UnavailableProvider()
    if args.strategy == "similarity":
        strategy = SimilarityStrategy(args.threshold)
        strategy_config = {"strategy": "similarity", "threshold": args.threshold}
    else:
        rules, rule_metadata = _load_rules()
        strategy = TriggerRuleStrategy(rules)
        strategy_config = {"strategy": "trigger-rules", **rule_metadata}
    facts = load_fact_definitions(expertise_data_root() / "fact-definitions.json")
    outcome = execute(
        args.role, task, framework_dir=framework, user_dir=user, flow_home=FLOW_HOME,
        provider=local_provider, strategy=strategy, strategy_config=strategy_config,
        fact_definitions=facts,
    )
    root = receipt_root(repo_root(), FLOW_HOME)
    receipt = write_pre(root, FLOW_HOME, outcome, normalized_task(task))
    result = dict(outcome)
    result["pre_receipt"] = {"digest": receipt["digest"]}
    result["runtime"] = {key: readiness[key] for key in ("state", "reason", "remedy", "environment_id") if key in readiness}
    return result


def query_command(args) -> int:
    try:
        return _emit(_query_result(args), args.json, 0)
    except (OSError, UnicodeError, ExpertiseCommandError, ValueError, TypeError) as error:
        return _emit({"state": "invalid_request", "reason": str(error)}, args.json, 2)


def brief_command(args) -> int:
    """Return a validated, role-isolated envelope for coordinator dispatch."""
    try:
        task_bytes = sys.stdin.buffer.read(32769)
        if len(task_bytes) > 32768:
            raise ExpertiseCommandError("advisory task exceeds 32768 UTF-8 bytes")
        task = task_bytes.decode("utf-8")
        if not task.strip():
            raise ExpertiseCommandError("advisory task on stdin must be non-empty")
        query_args = SimpleNamespace(
            role=args.role, strategy="similarity", threshold=0.70,
            framework_dir=None, user_dir=None,
        )
        outcome = _query_result(query_args, task_override=task)
        validate_outcome({key: outcome[key] for key in (
            "schema_version", "request_id", "role", "state", "cause",
            "eligibility", "ranking", "admission", "delivery",
        )})
        if outcome["role"] != args.role:
            raise ExpertiseCommandError("advisory outcome role does not match selected role")
        delivery = outcome["delivery"]
        admitted = outcome["state"] == "admitted" and delivery["state"] == "delivered"
        if admitted:
            required = (
                "@id", "name", "abstract", "flow:trigger", "flow:requiredBehavior",
                "flow:failureMode", "role", "source_layer", "method_layer",
                "lifecycle_state", "owner", "entry_digest",
            )
            for entry in delivery["entries"]:
                if not isinstance(entry, dict) or entry.get("role") != args.role:
                    raise ExpertiseCommandError("advisory entry role does not match selected role")
                if any(not entry.get(field) for field in required):
                    raise ExpertiseCommandError("advisory entry is incomplete")
        result = {
            "schema_version": 1, "state": "admitted" if admitted else outcome["state"],
            "role": args.role, "request_id": outcome["request_id"],
            "pre_receipt_digest": outcome["pre_receipt"]["digest"],
            "delivery_identity": delivery["identity"],
            "entry_ids": delivery["delivered_ids"] if admitted else [],
            "advisory_entries": delivery["entries"] if admitted else [],
            "limits": delivery["limits"],
            "reason": outcome["cause"] if admitted else delivery["reason"] if delivery["state"] in {"capped_failure", "invalid_envelope"} else outcome["cause"],
        }
        return _emit(result, args.json, 0)
    except (OSError, UnicodeError, ExpertiseCommandError, ValueError, TypeError, KeyError) as error:
        return _emit({"state": "invalid_request", "reason": str(error), "advisory_entries": []}, args.json, 2)


def disposition_command(args) -> int:
    try:
        if getattr(args, "handback_stdin", False):
            raw = sys.stdin.buffer.read(32769)
            if len(raw) > 32768:
                raise ExpertiseCommandError("disposition handback exceeds 32768 UTF-8 bytes")
            handback = json.loads(raw.decode("utf-8"))
            if not isinstance(handback, dict):
                raise ExpertiseCommandError("disposition handback must be a JSON object")
        else:
            handback = _read_object(Path(args.handback).expanduser().resolve(), "disposition handback")
        if handback.get("request_id") != args.request_id:
            raise ExpertiseCommandError("handback request_id does not match --request-id")
        root = receipt_root(repo_root(), FLOW_HOME)
        pre_path = root / f"{args.request_id}.pre.json"
        if not pre_path.is_file() or pre_path.is_symlink():
            raise ExpertiseCommandError("linked pre-agent receipt is missing")
        pre_bytes = pre_path.read_bytes()
        pre = json.loads(pre_bytes)
        pre_digest = hashlib.sha256(pre_bytes).hexdigest()
        if handback.get("pre_receipt_digest") != pre_digest:
            raise ExpertiseCommandError("handback pre_receipt_digest does not match the immutable pre-agent receipt")
        delivered_ids = pre.get("delivery", {}).get("delivered_ids")
        if not isinstance(delivered_ids, list):
            raise ExpertiseCommandError("pre-agent receipt has an invalid delivery record")
        if handback.get("identity") != pre.get("delivery", {}).get("identity"):
            raise ExpertiseCommandError("handback delivery identity does not match the pre-agent receipt")
        result = write_post(root, handback, delivered_ids)
        return _emit({"state": "complete", "request_id": args.request_id, "post_receipt": {"digest": result["digest"]}}, args.json, 0)
    except (OSError, json.JSONDecodeError, ExpertiseCommandError, ValueError, TypeError) as error:
        return _emit({"state": "invalid_request", "reason": str(error)}, args.json, 2)


def feedback_command(args) -> int:
    try:
        root = receipt_root(repo_root(), FLOW_HOME)
        if args.request_id is None:
            if args.category != "failure" or args.role not in ROLES or args.entry_id is not None:
                raise ExpertiseCommandError("unlinked feedback requires a role and failure category without an entry ID")
            role, pre_digest = args.role, None
        else:
            if not WORK_ID_RE.fullmatch(args.request_id):
                raise ExpertiseCommandError("invalid feedback request ID")
            pre_path = root / f"{args.request_id}.pre.json"
            if not pre_path.is_file() or pre_path.is_symlink():
                raise ExpertiseCommandError("linked pre-agent receipt is missing")
            pre_bytes = pre_path.read_bytes()
            pre = json.loads(pre_bytes)
            role = pre.get("role")
            if pre.get("kind") != "pre-agent" or pre.get("request_id") != args.request_id or role not in ROLES:
                raise ExpertiseCommandError("linked pre-agent receipt is invalid")
            if args.role is not None and args.role != role:
                raise ExpertiseCommandError("feedback role does not match linked request")
            delivered = pre.get("delivery", {}).get("delivered_ids")
            if not isinstance(delivered, list):
                raise ExpertiseCommandError("linked pre-agent receipt is invalid")
            if args.category in {"useful", "inapplicable"} and args.entry_id not in delivered:
                raise ExpertiseCommandError("feedback entry ID was not delivered in this request")
            if args.entry_id is not None and args.entry_id not in delivered:
                raise ExpertiseCommandError("feedback entry ID was not delivered in this request")
            if args.category in {"miss", "failure"} and args.entry_id is not None:
                raise ExpertiseCommandError("miss or failure feedback must not name a delivered entry")
            pre_digest = _sha256_bytes(pre_bytes)
        record = {
            "schema_version": 1, "kind": "user-feedback", "request_id": args.request_id,
            "pre_receipt_digest": pre_digest, "role": role,
            "lane": args.lane, "category": args.category, "entry_id": args.entry_id,
        }
        result = write_feedback(root, record)
        return _emit({"state": "recorded", "request_id": args.request_id, "feedback_digest": result["digest"]}, args.json, 0)
    except (OSError, json.JSONDecodeError, ExpertiseCommandError, ValueError, TypeError) as error:
        return _emit({"state": "invalid_request", "reason": str(error)}, args.json, 2)


def receipts_command(args) -> int:
    root = receipt_root(repo_root(), FLOW_HOME)
    try:
        result = inspect_receipts(root) if args.receipts_action == "inspect" else purge_receipts(root, days=args.days)
        return _emit(result, args.json, 0)
    except (OSError, ValueError, TypeError) as error:
        return _emit({"state": "invalid_request", "reason": str(error)}, args.json, 2)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _campaign_source_sha256(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative in CAMPAIGN_SOURCE_FILES:
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise ExpertiseCommandError(f"campaign source is missing or unsafe: {relative}")
        result[relative] = _sha256_bytes(path.read_bytes())
    return result


def _selected_configuration(run: Path) -> dict:
    path = run / "evidence" / "calibration-v1" / "scoring" / "selected-configuration.json"
    selected = _read_object(path, "selected calibration configuration")
    payload = {key: value for key, value in selected.items() if key != "executable_configuration_digest"}
    if selected.get("state") != "selected" or selected.get("executable_configuration_digest") != digest(payload):
        raise ExpertiseCommandError("selected calibration configuration is invalid")
    return selected


def _v2_independence_review(path: Path, manifest: dict) -> dict:
    review = _read_object(path, "evaluation-v2 split-independence review")
    deterministic_path = path.parent / "deterministic-receipt.json"
    deterministic = _read_object(
        deterministic_path, "evaluation-v2 deterministic split-independence receipt"
    )
    expected = {
        "schema_version", "state", "candidate_manifest_digest", "reference_manifest_digests",
        "deterministic_receipt_digest", "flag_count", "reviewed_flags", "unresolved_flags",
        "reviewer", "reviewed_at", "blinded_to_fixture_labels",
    }
    if set(review) != expected:
        raise ExpertiseCommandError("evaluation-v2 split-independence review has the wrong fields")
    if review.get("schema_version") != SCHEMA_VERSION or review.get("state") not in {"independent", "resolved"}:
        raise ExpertiseCommandError("evaluation-v2 split-independence review is not resolved")
    if review.get("candidate_manifest_digest") != digest(manifest):
        raise ExpertiseCommandError("split-independence review does not bind the evaluation-v2 candidate")
    if not isinstance(review.get("reference_manifest_digests"), list) or len(review["reference_manifest_digests"]) != 2:
        raise ExpertiseCommandError("split-independence review must bind evaluation-v1 and calibration-v1")
    if review.get("deterministic_receipt_digest") != digest(deterministic):
        raise ExpertiseCommandError("split-independence review does not bind its deterministic receipt")
    if (
        deterministic.get("candidate_manifest_digest") != digest(manifest)
        or deterministic.get("reference_manifest_digests") != review.get("reference_manifest_digests")
    ):
        raise ExpertiseCommandError("deterministic split-independence receipt has changed inputs")
    if review.get("blinded_to_fixture_labels") is not True:
        raise ExpertiseCommandError("split-independence reviewer must be blinded to fixture labels")
    if review.get("unresolved_flags") != []:
        raise ExpertiseCommandError("split-independence review contains unresolved flags")
    rows = review.get("reviewed_flags")
    if not isinstance(rows, list) or review.get("flag_count") != len(rows):
        raise ExpertiseCommandError("split-independence reviewed flag count is inconsistent")
    deterministic_flags = deterministic.get("flags")
    if not isinstance(deterministic_flags, list) or len(deterministic_flags) != len(rows):
        raise ExpertiseCommandError("split-independence review does not account for every deterministic flag")
    flag_keys = {
        (
            row.get("candidate_id"), row.get("reference_split"), row.get("reference_id"),
            tuple(row.get("kinds", [])) if isinstance(row.get("kinds"), list) else (),
        )
        for row in deterministic_flags if isinstance(row, dict)
    }
    for row in rows:
        if (
            not isinstance(row, dict)
            or row.get("disposition") != "distinct"
            or not isinstance(row.get("rationale"), str)
            or not row["rationale"].strip()
        ):
            raise ExpertiseCommandError("split-independence flags require a resolved disposition and rationale")
        key = (
            row.get("candidate_id"), row.get("reference_split"), row.get("reference_id"),
            tuple(row.get("kinds", [])) if isinstance(row.get("kinds"), list) else (),
        )
        if key not in flag_keys:
            raise ExpertiseCommandError("split-independence review names a flag outside the deterministic receipt")
    if not isinstance(review.get("reviewer"), str) or not review["reviewer"].strip():
        raise ExpertiseCommandError("split-independence review requires a reviewer")
    return review


def _campaign_identity(framework_override: str | None = None) -> dict:
    readiness = runtime_status(FLOW_HOME)
    if readiness.get("state") != "ready":
        raise ExpertiseCommandError(
            f"expertise runtime is not ready: {readiness.get('reason', 'unknown')}"
        )
    framework, user = _runtime_paths(SimpleNamespace(framework_dir=framework_override, user_dir=None))
    snapshot = canonical_snapshot(ROLES, framework, user)
    local_provider = load_provider(FLOW_HOME)
    projection = projection_identity(snapshot, local_provider)
    projection_state = inspect_projection(FLOW_HOME, projection["digest"])
    if projection_state.get("state") != "ready":
        raise ExpertiseCommandError(
            f"expertise projection is not current: {projection_state.get('reason', projection_state.get('state'))}"
        )
    model = _read_object(expertise_data_root() / "model-manifest.json", "model manifest")
    lock = _read_object(expertise_data_root() / "runtime-lock.json", "runtime lock")
    facts = load_fact_definitions(expertise_data_root() / "fact-definitions.json")
    rules = _read_object(expertise_data_root() / "trigger-rules.json", "trigger rules")
    return {
        "canonical": {
            "corpus_digest": snapshot["corpus_digest"],
            "lifecycle_revision": snapshot["lifecycle_revision"],
            "entry_serializer_revision": snapshot["entry_serializer_revision"],
        },
        "provider": {
            "environment_id": readiness["environment_id"],
            "provider_revision": readiness["provider_revision"],
            "model_artifact_digest": readiness["model_artifact_digest"],
            "runtime_revision": readiness["runtime_revision"],
            "model_manifest_digest": digest(model),
            "runtime_lock_digest": digest(lock),
        },
        "projection_identity": projection["digest"],
        "facts": {
            "definitions_digest": digest(facts),
            "derivation_revision": FACT_DERIVATION_REVISION,
            "definitions_revision": facts["revision"],
            "normalizer_revision": facts["normalizer_revision"],
        },
        "contracts": {
            "schema_version": SCHEMA_VERSION,
            "admission_input_revision": ADMISSION_INPUT_REVISION,
            "packing_revision": PACKING_REVISION,
            "envelope_revision": ENVELOPE_REVISION,
            "disposition_contract_revision": DISPOSITION_CONTRACT_REVISION,
            "ranker_revision": "exact-cosine-v1",
        },
        "limits": dict(DEFAULT_LIMITS),
        "candidates": {
            "similarity_grid": list(SIMILARITY_GRID),
            "trigger_rules_digest": digest(rules),
            "trigger_rules_revision": rules.get("revision"),
        },
    }


def build_freeze_receipt(
    manifest: dict,
    manifest_bytes: bytes,
    campaign_identity: dict,
    *,
    approved_digest: str,
    approved_by: str,
    approved_at: str,
    independence_review: dict | None = None,
    source_sha256: dict[str, str] | None = None,
) -> dict:
    actual_digest = digest(manifest)
    if approved_digest != actual_digest:
        raise ExpertiseCommandError(
            f"approved digest does not match candidate manifest: expected {actual_digest}"
        )
    if not isinstance(approved_by, str) or not approved_by.strip():
        raise ExpertiseCommandError("approved-by must identify the approving engineer")
    fixtures = []
    for fixture in manifest["fixtures"]:
        fixtures.append({
            "fixture_id": fixture["id"],
            "query_digest": digest(normalized_task(fixture["task"])),
            "fixture_digest": digest(fixture),
        })
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "state": "frozen",
        "split": manifest["split"],
        "candidate_manifest_digest": actual_digest,
        "candidate_manifest_file_sha256": _sha256_bytes(manifest_bytes),
        "fixture_digests": fixtures,
        "evaluation_v1_digests": dict(EVALUATION_V1_DIGESTS),
        "campaign_identity": campaign_identity,
        "approval": {
            "approved_by": approved_by.strip(),
            "approved_at": approved_at,
            "approved_candidate_digest": approved_digest,
        },
    }
    if manifest["split"] == "evaluation-v2":
        if independence_review is None or source_sha256 is None:
            raise ExpertiseCommandError("evaluation-v2 freeze requires independence review and source hashes")
        receipt["selected_configuration"] = {
            "candidate_id": manifest["selected_candidate_id"],
            "executable_configuration_digest": manifest["selected_configuration_digest"],
        }
        receipt["independence_review_digest"] = digest(independence_review)
        receipt["source_sha256"] = source_sha256
    return dict(receipt, freeze_receipt_digest=digest(receipt))


def _write_private_new(path: Path, payload: bytes, run_root: Path) -> None:
    path = _contained_no_symlink(path, run_root)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(path, 0o600)
    except BaseException:
        try:
            path.unlink()
        except OSError:
            pass
        raise


def _frozen_paths(run: Path, split: str) -> tuple[Path, Path]:
    root = run / "evidence" / split / "frozen"
    return root / "candidate-manifest.json", root / "freeze-receipt.json"


def verify_campaign_freeze(run: Path, split: str) -> dict:
    manifest_path, receipt_path = _frozen_paths(run, split)
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    receipt = json.loads(receipt_path.read_bytes())
    problems: list[str] = []
    validation = validate_fixture_manifest(
        manifest, _corpus_inventory(_framework(repo_root(), None))
    )
    if validation["state"] != "valid":
        problems.extend(validation["problems"])
    if receipt.get("state") != "frozen" or receipt.get("split") != split:
        problems.append("freeze receipt state or split is invalid")
    receipt_payload = {key: value for key, value in receipt.items() if key != "freeze_receipt_digest"}
    if receipt.get("freeze_receipt_digest") != digest(receipt_payload):
        problems.append("freeze receipt digest mismatch")
    if receipt.get("candidate_manifest_digest") != digest(manifest):
        problems.append("frozen candidate manifest digest mismatch")
    if receipt.get("candidate_manifest_file_sha256") != _sha256_bytes(manifest_bytes):
        problems.append("frozen candidate manifest file digest mismatch")
    expected_fixtures = [
        {"fixture_id": row["id"], "query_digest": digest(normalized_task(row["task"])), "fixture_digest": digest(row)}
        for row in manifest["fixtures"]
    ]
    if receipt.get("fixture_digests") != expected_fixtures:
        problems.append("frozen fixture or query digest mismatch")
    approval = receipt.get("approval")
    if not isinstance(approval, dict) or approval.get("approved_candidate_digest") != digest(manifest):
        problems.append("freeze approval does not bind the candidate manifest")
    current_identity = _campaign_identity()
    if receipt.get("campaign_identity") != current_identity:
        problems.append("campaign identity changed after freeze")
    if split == "evaluation-v2":
        try:
            selected = _selected_configuration(run)
            if (
                manifest.get("selected_candidate_id") != selected.get("candidate_id")
                or manifest.get("selected_configuration_digest") != selected.get("executable_configuration_digest")
            ):
                problems.append("evaluation-v2 does not bind the selected calibration configuration")
        except (OSError, ExpertiseCommandError, ValueError, TypeError) as error:
            problems.append(str(error))
        if receipt.get("source_sha256") != _campaign_source_sha256(repo_root()):
            problems.append("campaign source changed after evaluation-v2 freeze")
    return {
        "state": "valid" if not problems else "invalid",
        "split": split,
        "candidate_manifest_digest": digest(manifest),
        "freeze_receipt_digest": receipt.get("freeze_receipt_digest"),
        "fixture_count": len(manifest.get("fixtures", [])),
        "problems": problems,
    }


def _write_json_document(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _mutate_framework(source: Path, destination: Path, mutation: dict, query_role: str) -> None:
    shutil.copytree(source, destination)
    target_id = mutation["entry_id"]
    found_path: Path | None = None
    found_document: dict | None = None
    found_entry: dict | None = None
    for path in sorted((destination / "expertise").glob("*.jsonld")):
        document = _read_object(path, "campaign mutation corpus")
        for entry in document.get("@graph", []):
            if isinstance(entry, dict) and entry.get("@id") == target_id:
                found_path, found_document, found_entry = path, document, entry
                break
        if found_entry is not None:
            break
    if found_entry is None or found_path is None or found_document is None:
        raise ExpertiseCommandError(f"integrity mutation target is missing: {target_id}")
    kind = mutation["kind"]
    if kind == "lifecycle_not_current":
        found_entry.pop("flow:lifecycle", None)
        _write_json_document(found_path, found_document)
    elif kind == "lifecycle_withdrawn":
        found_entry["flow:lifecycle"]["state"] = "withdrawn"
        _write_json_document(found_path, found_document)
    elif kind == "role_mismatch":
        found_document["@graph"].remove(found_entry)
        _write_json_document(found_path, found_document)
        destination_role = next(role for role in sorted(ROLES) if role != query_role)
        destination_path = destination / "expertise" / f"{destination_role}.jsonld"
        destination_document = _read_object(destination_path, "campaign role-mutation corpus")
        moved = json.loads(json.dumps(found_entry))
        moved["audience"]["audienceType"] = destination_role
        destination_document["@graph"].append(moved)
        _write_json_document(destination_path, destination_document)
    elif kind == "invalid_graph" and mutation.get("mutation") == "duplicate_entry_id":
        found_document["@graph"].append(json.loads(json.dumps(found_entry)))
        _write_json_document(found_path, found_document)
    else:
        raise ExpertiseCommandError(f"unsupported integrity mutation: {kind}")


def _candidate_strategies(manifest: dict) -> list[tuple[str, object, dict]]:
    result: list[tuple[str, object, dict]] = []
    for threshold in manifest["preregistered_similarity_grid"]:
        result.append((
            f"similarity:{threshold:.2f}", SimilarityStrategy(threshold),
            {"strategy": "similarity", "threshold": threshold},
        ))
    rules, metadata = _load_rules()
    result.append((
        "trigger-rules", TriggerRuleStrategy(rules),
        {"strategy": "trigger-rules", **metadata},
    ))
    return result


def _campaign_outcome(
    fixture: dict,
    *,
    candidate_id: str,
    strategy: object,
    strategy_config: dict,
    framework: Path,
    user: Path | None,
    provider: object,
    facts: dict,
) -> dict:
    request_id = f"campaign-{digest({'candidate': candidate_id, 'fixture': fixture['id']})[:32]}"
    mutation = fixture.get("integrity_mutation")
    if not isinstance(mutation, dict):
        return execute(
            fixture["role"], fixture["task"], framework_dir=framework, user_dir=user,
            flow_home=FLOW_HOME, provider=provider, strategy=strategy,
            strategy_config=strategy_config, fact_definitions=facts, request_id=request_id,
        )
    with tempfile.TemporaryDirectory(prefix="flow-expertise-mutation-") as temporary:
        root = Path(temporary)
        mutated_framework = root / "framework"
        _mutate_framework(framework, mutated_framework, mutation, fixture["role"])
        mutated_home = root / "flow-home"
        if mutation["kind"] != "invalid_graph":
            snapshot = canonical_snapshot(ROLES, mutated_framework, user)
            publish_projection(
                mutated_home, snapshot, provider,
                verify_snapshot=lambda: canonical_snapshot(ROLES, mutated_framework, user)["corpus_digest"],
            )
        return execute(
            fixture["role"], fixture["task"], framework_dir=mutated_framework,
            user_dir=user, flow_home=mutated_home, provider=provider, strategy=strategy,
            strategy_config=strategy_config, fact_definitions=facts, request_id=request_id,
        )


def retrieve_calibration(run: Path) -> dict:
    verified = verify_campaign_freeze(run, "calibration-v1")
    if verified["state"] != "valid":
        raise ExpertiseCommandError("calibration freeze is invalid")
    manifest_path, _ = _frozen_paths(run, "calibration-v1")
    manifest = _read_object(manifest_path, "frozen calibration manifest")
    framework, user = _runtime_paths(SimpleNamespace(framework_dir=None, user_dir=None))
    provider = load_provider(FLOW_HOME)
    facts = load_fact_definitions(expertise_data_root() / "fact-definitions.json")
    scorecards = []
    work_items = []
    for candidate_id, strategy, strategy_config in _candidate_strategies(manifest):
        outcomes: dict[str, dict] = {}
        for fixture in manifest["fixtures"]:
            outcome = _campaign_outcome(
                fixture, candidate_id=candidate_id, strategy=strategy,
                strategy_config=strategy_config, framework=framework, user=user,
                provider=provider, facts=facts,
            )
            outcomes[fixture["id"]] = outcome
            if outcome["delivery"]["delivered_ids"]:
                work_items.append({
                    "work_item_id": digest({"candidate": candidate_id, "fixture": fixture["id"], "delivery": outcome["delivery"]["identity"]}),
                    "candidate_id": candidate_id,
                    "fixture_id": fixture["id"],
                    "role": fixture["role"],
                    "task": fixture["task"],
                    "request_id": outcome["request_id"],
                    "delivery_identity": outcome["delivery"]["identity"],
                    "delivered_ids": outcome["delivery"]["delivered_ids"],
                    "entries": outcome["delivery"]["entries"],
                    "disposition_state": "pending",
                })
        scorecards.append(score_candidate(
            manifest, candidate_id, lambda fixture, values=outcomes: values[fixture["id"]]
        ))
    safe_result = {
        "schema_version": SCHEMA_VERSION,
        "state": "awaiting_dispositions" if work_items else "retrieval_complete",
        "split": "calibration-v1",
        "manifest_digest": digest(manifest),
        "freeze_receipt_digest": verified["freeze_receipt_digest"],
        "candidate_ids": [row["candidate_id"] for row in scorecards],
        "scorecards": scorecards,
        "work_item_count": len(work_items),
    }
    return {"result": safe_result, "work_items": {"schema_version": SCHEMA_VERSION, "items": work_items}}


def finalize_calibration(run: Path, dispositions_path: str | None = None) -> dict:
    verified = verify_campaign_freeze(run, "calibration-v1")
    if verified["state"] != "valid":
        raise ExpertiseCommandError("calibration freeze is invalid")
    manifest_path, receipt_path = _frozen_paths(run, "calibration-v1")
    manifest = _read_object(manifest_path, "frozen calibration manifest")
    freeze_receipt = _read_object(receipt_path, "calibration freeze receipt")
    retrieval_path = run / "evidence" / "calibration-v1" / "scoring" / "retrieval-results.json"
    retrieval = _read_object(retrieval_path, "calibration retrieval results", maximum_bytes=32 * 1024 * 1024)
    if (
        retrieval.get("manifest_digest") != digest(manifest)
        or retrieval.get("freeze_receipt_digest") != verified["freeze_receipt_digest"]
    ):
        raise ExpertiseCommandError("calibration retrieval results do not bind the current freeze")
    dispositions: dict[tuple[str, str], dict] = {}
    if dispositions_path:
        document = _read_object(Path(dispositions_path).expanduser().resolve(), "calibration dispositions")
        items = document.get("items")
        if not isinstance(items, list):
            raise ExpertiseCommandError("calibration dispositions must contain an items list")
        for item in items:
            if not isinstance(item, dict):
                raise ExpertiseCommandError("calibration disposition item must be an object")
            key = (item.get("candidate_id"), item.get("fixture_id"))
            if not all(isinstance(value, str) and value for value in key) or key in dispositions:
                raise ExpertiseCommandError("calibration dispositions contain an invalid or duplicate key")
            dispositions[key] = item
    scorecards = []
    expected_candidates = [candidate_id for candidate_id, _, _ in _candidate_strategies(manifest)]
    retained = retrieval.get("scorecards")
    if not isinstance(retained, list) or [row.get("candidate_id") for row in retained if isinstance(row, dict)] != expected_candidates:
        raise ExpertiseCommandError("calibration retrieval candidate set or order changed")
    for retained_card in retained:
        candidate_id = retained_card["candidate_id"]
        retained_rows = retained_card.get("rows")
        if not isinstance(retained_rows, list):
            raise ExpertiseCommandError("calibration retrieval result rows are missing")
        outcomes = {row["fixture_id"]: row["safe_result"] for row in retained_rows}
        if set(outcomes) != {fixture["id"] for fixture in manifest["fixtures"]}:
            raise ExpertiseCommandError("calibration retrieval rows do not match the frozen fixtures")
        candidate_dispositions = {
            fixture_id: value for (candidate, fixture_id), value in dispositions.items()
            if candidate == candidate_id
        }
        scorecards.append(score_candidate(
            manifest, candidate_id,
            lambda fixture, values=outcomes: values[fixture["id"]],
            candidate_dispositions,
        ))
    selection = select_candidate(scorecards)
    winner = selection.get("winner")
    selected_config: dict | None = None
    if isinstance(winner, str):
        if winner.startswith("similarity:"):
            config = {"strategy": "similarity", "threshold": float(winner.split(":", 1)[1])}
            strategy_revision = SimilarityStrategy(config["threshold"]).revision
        elif winner == "trigger-rules":
            _, metadata = _load_rules()
            config = {"strategy": "trigger-rules", **metadata}
            strategy_revision = TriggerRuleStrategy(_load_rules()[0]).revision
        else:
            raise ExpertiseCommandError("selector returned an undeclared candidate")
        selected_payload = {
            "schema_version": SCHEMA_VERSION,
            "state": "selected",
            "split": "calibration-v1",
            "candidate_id": winner,
            "strategy_revision": strategy_revision,
            "strategy_config": config,
            "strategy_config_digest": digest(config),
            "campaign_identity": freeze_receipt["campaign_identity"],
            "manifest_digest": digest(manifest),
            "freeze_receipt_digest": verified["freeze_receipt_digest"],
            "selection_digest": selection["selection_digest"],
        }
        selected_config = dict(selected_payload, executable_configuration_digest=digest(selected_payload))
    return {
        "scorecards": {"schema_version": SCHEMA_VERSION, "split": "calibration-v1", "scorecards": scorecards},
        "selection": selection,
        "selected_configuration": selected_config,
    }


def _heldout_strategy(run: Path, manifest: dict) -> tuple[str, object, dict]:
    selected = _selected_configuration(run)
    candidate_id = selected["candidate_id"]
    if (
        manifest.get("selected_candidate_id") != candidate_id
        or manifest.get("selected_configuration_digest") != selected["executable_configuration_digest"]
    ):
        raise ExpertiseCommandError("evaluation-v2 selected configuration binding changed")
    config = selected.get("strategy_config")
    if not isinstance(config, dict):
        raise ExpertiseCommandError("selected calibration strategy configuration is missing")
    if candidate_id.startswith("similarity:") and config.get("strategy") == "similarity":
        threshold = config.get("threshold")
        if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
            raise ExpertiseCommandError("selected similarity threshold is invalid")
        return candidate_id, SimilarityStrategy(float(threshold)), dict(config)
    if candidate_id == "trigger-rules" and config.get("strategy") == "trigger-rules":
        rules, metadata = _load_rules()
        expected = {"strategy": "trigger-rules", **metadata}
        if config != expected:
            raise ExpertiseCommandError("selected trigger-rule configuration changed")
        return candidate_id, TriggerRuleStrategy(rules), dict(config)
    raise ExpertiseCommandError("selected calibration strategy is undeclared")


def _percentile_95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, (95 * len(ordered) + 99) // 100 - 1)]


def _persistent_expertise_bytes() -> int:
    root = FLOW_HOME / "cache" / "expertise"
    if not root.exists():
        return 0
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file() and not path.is_symlink())


def _environment_evidence(
    path: str | None, *, manifest_digest: str, configuration_digest: str,
) -> dict:
    if not path:
        return {"state": "unverified", "missing_environment_ids": sorted(REQUIRED_ENVIRONMENTS)}
    document = _read_object(Path(path).expanduser().resolve(), "held-out environment evidence")
    if set(document) != {"schema_version", "manifest_digest", "selected_configuration_digest", "cells"}:
        raise ExpertiseCommandError("held-out environment evidence has the wrong fields")
    if (
        document.get("schema_version") != SCHEMA_VERSION
        or document.get("manifest_digest") != manifest_digest
        or document.get("selected_configuration_digest") != configuration_digest
    ):
        raise ExpertiseCommandError("held-out environment evidence does not bind the frozen campaign")
    cells = document.get("cells")
    if not isinstance(cells, list):
        raise ExpertiseCommandError("held-out environment evidence cells must be a list")
    by_id: dict[str, dict] = {}
    for cell in cells:
        if not isinstance(cell, dict) or set(cell) != {
            "id", "status", "repeatability", "fixture_oracles", "warm_p95_seconds",
            "cold_p95_seconds", "persistent_bytes", "evidence_digest",
        }:
            raise ExpertiseCommandError("held-out environment evidence cell has the wrong fields")
        cell_id = cell.get("id")
        if not isinstance(cell_id, str) or cell_id in by_id:
            raise ExpertiseCommandError("held-out environment evidence has an invalid or duplicate cell")
        by_id[cell_id] = cell
    missing = sorted(REQUIRED_ENVIRONMENTS - set(by_id))
    extras = sorted(set(by_id) - REQUIRED_ENVIRONMENTS)
    failed = sorted(
        cell_id for cell_id, cell in by_id.items()
        if (
            cell.get("status") != "passed"
            or cell.get("repeatability") != "identical"
            or cell.get("fixture_oracles") != "passed"
            or not isinstance(cell.get("warm_p95_seconds"), (int, float))
            or isinstance(cell.get("warm_p95_seconds"), bool)
            or cell["warm_p95_seconds"] > 1.0
            or not isinstance(cell.get("cold_p95_seconds"), (int, float))
            or isinstance(cell.get("cold_p95_seconds"), bool)
            or cell["cold_p95_seconds"] > 30.0
            or not isinstance(cell.get("persistent_bytes"), int)
            or isinstance(cell.get("persistent_bytes"), bool)
            or cell["persistent_bytes"] >= 1_000_000_000
            or not re.fullmatch(r"[0-9a-f]{64}", str(cell.get("evidence_digest", "")))
        )
    )
    return {
        "state": "passed" if not missing and not extras and not failed else "unverified",
        "missing_environment_ids": missing,
        "unexpected_environment_ids": extras,
        "failed_environment_ids": failed,
        "cell_count": len(by_id),
        "evidence_digest": digest(document),
    }


def retrieve_heldout(run: Path) -> dict:
    verified = verify_campaign_freeze(run, "evaluation-v2")
    if verified["state"] != "valid":
        raise ExpertiseCommandError("evaluation-v2 freeze is invalid")
    manifest_path, _ = _frozen_paths(run, "evaluation-v2")
    manifest = _read_object(manifest_path, "frozen evaluation-v2 manifest")
    candidate_id, strategy, strategy_config = _heldout_strategy(run, manifest)
    framework, user = _runtime_paths(SimpleNamespace(framework_dir=None, user_dir=None))
    cold_started = time.perf_counter()
    provider = load_provider(FLOW_HOME)
    facts = load_fact_definitions(expertise_data_root() / "fact-definitions.json")
    cold_seconds = time.perf_counter() - cold_started
    repeats: list[dict] = []
    work_items: list[dict] = []
    for repeat_index in (1, 2):
        outcomes: dict[str, dict] = {}
        elapsed: list[float] = []
        for fixture in manifest["fixtures"]:
            started = time.perf_counter()
            outcome = _campaign_outcome(
                fixture, candidate_id=candidate_id, strategy=strategy,
                strategy_config=strategy_config, framework=framework, user=user,
                provider=provider, facts=facts,
            )
            elapsed.append(time.perf_counter() - started)
            outcomes[fixture["id"]] = outcome
            if outcome["delivery"]["delivered_ids"]:
                work_items.append({
                    "work_item_id": digest({
                        "repeat": repeat_index, "candidate": candidate_id,
                        "fixture": fixture["id"], "delivery": outcome["delivery"]["identity"],
                    }),
                    "repeat": repeat_index,
                    "candidate_id": candidate_id,
                    "fixture_id": fixture["id"],
                    "role": fixture["role"],
                    "task": fixture["task"],
                    "request_id": outcome["request_id"],
                    "delivery_identity": outcome["delivery"]["identity"],
                    "delivered_ids": outcome["delivery"]["delivered_ids"],
                    "entries": outcome["delivery"]["entries"],
                    "expected_disposition": fixture["expected"]["disposition"],
                    "behavior_oracle": fixture["behavior_oracle"],
                    "disposition_state": "pending",
                })
        scorecard = score_candidate(
            manifest, candidate_id,
            lambda fixture, values=outcomes: values[fixture["id"]],
        )
        repeats.append({
            "repeat": repeat_index,
            "scorecard": scorecard,
            "timing": {
                "fixture_count": len(elapsed),
                "warm_p95_seconds": round(_percentile_95(elapsed), 6),
                "warm_max_seconds": round(max(elapsed, default=0.0), 6),
            },
        })
    repeat_check = repeatable(repeats[0]["scorecard"], repeats[1]["scorecard"])
    retrieval_failures = sorted({
        row["fixture_id"]
        for repeat_row in repeats
        for row in repeat_row["scorecard"]["rows"]
        if (
            row["retrieval_pass"] is not True
            or row["leaked_prohibited_ids"]
            or row["untraceable_candidate_ids"]
        )
    })
    readiness = runtime_status(FLOW_HOME)
    state = "stop" if retrieval_failures or repeat_check["state"] != "identical" else (
        "awaiting_dispositions" if work_items else "retrieval_complete"
    )
    result = {
        "schema_version": SCHEMA_VERSION,
        "state": state,
        "split": "evaluation-v2",
        "candidate_id": candidate_id,
        "selected_configuration_digest": manifest["selected_configuration_digest"],
        "manifest_digest": digest(manifest),
        "freeze_receipt_digest": verified["freeze_receipt_digest"],
        "environment_id": readiness.get("environment_id"),
        "repeats": repeats,
        "repeatability": repeat_check,
        "retrieval_failure_fixture_ids": retrieval_failures,
        "work_item_count": len(work_items),
        "performance": {
            "cold_provider_load_seconds": round(cold_seconds, 6),
            "cold_full_query_state": "unverified",
            "persistent_bytes": _persistent_expertise_bytes(),
            "persistent_limit_bytes": 1_000_000_000,
        },
    }
    return {"result": result, "work_items": {"schema_version": SCHEMA_VERSION, "items": work_items}}


def _heldout_dispositions(path: str | None, candidate_id: str) -> dict[tuple[int, str], dict]:
    if not path:
        return {}
    document = _read_object(Path(path).expanduser().resolve(), "held-out dispositions")
    items = document.get("items")
    if not isinstance(items, list):
        raise ExpertiseCommandError("held-out dispositions must contain an items list")
    result: dict[tuple[int, str], dict] = {}
    for item in items:
        if not isinstance(item, dict) or item.get("candidate_id") != candidate_id:
            raise ExpertiseCommandError("held-out disposition has the wrong candidate")
        key = (item.get("repeat"), item.get("fixture_id"))
        if (
            not isinstance(key[0], int) or isinstance(key[0], bool) or key[0] not in {1, 2}
            or not isinstance(key[1], str) or not key[1] or key in result
        ):
            raise ExpertiseCommandError("held-out dispositions contain an invalid or duplicate key")
        result[key] = item
    return result


def finalize_heldout(
    run: Path,
    dispositions_path: str | None = None,
    environment_evidence_path: str | None = None,
) -> dict:
    verified = verify_campaign_freeze(run, "evaluation-v2")
    if verified["state"] != "valid":
        raise ExpertiseCommandError("evaluation-v2 freeze is invalid")
    manifest_path, _ = _frozen_paths(run, "evaluation-v2")
    manifest = _read_object(manifest_path, "frozen evaluation-v2 manifest")
    candidate_id, _, _ = _heldout_strategy(run, manifest)
    retrieval_path = run / "evidence" / "evaluation-v2" / "scoring" / "retrieval-results.json"
    retrieval = _read_object(retrieval_path, "held-out retrieval results", maximum_bytes=32 * 1024 * 1024)
    if (
        retrieval.get("manifest_digest") != digest(manifest)
        or retrieval.get("freeze_receipt_digest") != verified["freeze_receipt_digest"]
        or retrieval.get("candidate_id") != candidate_id
    ):
        raise ExpertiseCommandError("held-out retrieval results do not bind the current freeze")
    dispositions = _heldout_dispositions(dispositions_path, candidate_id)
    scorecards: list[dict] = []
    retained_repeats = retrieval.get("repeats")
    if not isinstance(retained_repeats, list) or [row.get("repeat") for row in retained_repeats if isinstance(row, dict)] != [1, 2]:
        raise ExpertiseCommandError("held-out retrieval must contain exactly two ordered repeats")
    for repeat_row in retained_repeats:
        retained = repeat_row.get("scorecard")
        rows = retained.get("rows") if isinstance(retained, dict) else None
        if not isinstance(rows, list):
            raise ExpertiseCommandError("held-out retrieval scorecard rows are missing")
        outcomes = {row["fixture_id"]: row["safe_result"] for row in rows}
        if set(outcomes) != {fixture["id"] for fixture in manifest["fixtures"]}:
            raise ExpertiseCommandError("held-out retrieval rows do not match the frozen fixtures")
        repeat_index = repeat_row["repeat"]
        per_repeat = {
            fixture_id: value for (repeat_value, fixture_id), value in dispositions.items()
            if repeat_value == repeat_index
        }
        scorecards.append(score_candidate(
            manifest, candidate_id,
            lambda fixture, values=outcomes: values[fixture["id"]],
            per_repeat,
        ))
    repeat_check = repeatable(scorecards[0], scorecards[1])
    all_pass = all(
        card["complete"] and not card["hard_failures"] and all(row["passed"] for row in card["rows"])
        for card in scorecards
    )
    environment = _environment_evidence(
        environment_evidence_path,
        manifest_digest=digest(manifest),
        configuration_digest=manifest["selected_configuration_digest"],
    )
    qualified = all_pass and repeat_check["state"] == "identical" and environment["state"] == "passed"
    if not all_pass:
        reason = "fixture_oracle_failure"
    elif repeat_check["state"] != "identical":
        reason = "repeatability_failure"
    elif environment["state"] != "passed":
        reason = "environment_evidence_incomplete"
    else:
        reason = "all_qualification_gates_passed"
    decision = {
        "schema_version": SCHEMA_VERSION,
        "split": "evaluation-v2",
        "state": "qualified_disabled" if qualified else "stop",
        "reason": reason,
        "candidate_id": candidate_id,
        "selected_configuration_digest": manifest["selected_configuration_digest"],
        "manifest_digest": digest(manifest),
        "freeze_receipt_digest": verified["freeze_receipt_digest"],
        "repeatability": repeat_check,
        "all_fixture_oracles_passed": all_pass,
        "environment_evidence": environment,
        "failed_fixture_ids": sorted({
            row["fixture_id"] for card in scorecards for row in card["rows"] if not row["passed"]
        }),
        "missing_disposition_fixture_ids": sorted({
            row["fixture_id"] for card in scorecards for row in card["rows"] if not row["complete"]
        }),
    }
    return {
        "scorecards": {"schema_version": SCHEMA_VERSION, "split": "evaluation-v2", "repeats": scorecards},
        "repeatability": repeat_check,
        "decision": decision,
    }


def campaign_command(args) -> int:
    try:
        if not WORK_ID_RE.fullmatch(args.work_id):
            raise ExpertiseCommandError("invalid work id")
        run = repo_root() / ".flow" / "runs" / args.work_id
        if not run.is_dir():
            raise ExpertiseCommandError(f"run does not exist: {args.work_id}")
        if args.campaign_action == "verify-freeze":
            result = verify_campaign_freeze(run, args.split)
            return _emit(result, args.json, 0 if result["state"] == "valid" else 3)
        if args.campaign_action == "retrieve-calibration":
            scoring = run / "evidence" / "calibration-v1" / "scoring"
            result_path = scoring / "retrieval-results.json"
            work_path = scoring / "disposition-work-items.json"
            if result_path.exists() or work_path.exists():
                raise ExpertiseCommandError(
                    "calibration retrieval evidence already exists; preserve it or create a new campaign revision"
                )
            campaign = retrieve_calibration(run)
            _write_private_new(
                result_path,
                (json.dumps(campaign["result"], indent=2, sort_keys=True) + "\n").encode(),
                run,
            )
            try:
                _write_private_new(
                    work_path,
                    (json.dumps(campaign["work_items"], indent=2, sort_keys=True) + "\n").encode(),
                    run,
                )
            except BaseException:
                result_path.unlink(missing_ok=True)
                raise
            summary = {
                key: campaign["result"][key]
                for key in ("state", "split", "manifest_digest", "freeze_receipt_digest", "candidate_ids", "work_item_count")
            }
            return _emit(summary, args.json, 0)
        if args.campaign_action == "finalize-calibration":
            scoring = run / "evidence" / "calibration-v1" / "scoring"
            scorecards_path = scoring / "scorecards.json"
            selection_path = scoring / "selection.json"
            selected_path = scoring / "selected-configuration.json"
            if any(path.exists() for path in (scorecards_path, selection_path, selected_path)):
                raise ExpertiseCommandError(
                    "calibration selection evidence already exists; preserve it or create a new campaign revision"
                )
            final = finalize_calibration(run, args.dispositions)
            payloads = (
                (scorecards_path, final["scorecards"]),
                (selection_path, final["selection"]),
            )
            written: list[Path] = []
            try:
                for path, value in payloads:
                    _write_private_new(path, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode(), run)
                    written.append(path)
                if final["selected_configuration"] is not None:
                    _write_private_new(
                        selected_path,
                        (json.dumps(final["selected_configuration"], indent=2, sort_keys=True) + "\n").encode(),
                        run,
                    )
                    written.append(selected_path)
            except BaseException:
                for path in written:
                    path.unlink(missing_ok=True)
                raise
            result = dict(final["selection"])
            if final["selected_configuration"] is not None:
                result["executable_configuration_digest"] = final["selected_configuration"]["executable_configuration_digest"]
            return _emit(result, args.json, 0 if result["state"] == "selected" else 3)
        if args.campaign_action == "retrieve-heldout":
            scoring = run / "evidence" / "evaluation-v2" / "scoring"
            result_path = scoring / "retrieval-results.json"
            work_path = scoring / "disposition-work-items.json"
            if result_path.exists() or work_path.exists():
                raise ExpertiseCommandError(
                    "held-out retrieval evidence already exists; preserve it or create a new evaluation revision"
                )
            campaign = retrieve_heldout(run)
            _write_private_new(
                result_path,
                (json.dumps(campaign["result"], indent=2, sort_keys=True) + "\n").encode(),
                run,
            )
            try:
                _write_private_new(
                    work_path,
                    (json.dumps(campaign["work_items"], indent=2, sort_keys=True) + "\n").encode(),
                    run,
                )
            except BaseException:
                result_path.unlink(missing_ok=True)
                raise
            summary = {
                key: campaign["result"][key]
                for key in (
                    "state", "split", "candidate_id", "manifest_digest",
                    "freeze_receipt_digest", "environment_id", "repeatability",
                    "retrieval_failure_fixture_ids", "work_item_count", "performance",
                )
            }
            return _emit(summary, args.json, 0 if summary["state"] != "stop" else 3)
        if args.campaign_action == "finalize-heldout":
            scoring = run / "evidence" / "evaluation-v2" / "scoring"
            scorecards_path = scoring / "scorecards.json"
            repeatability_path = scoring / "repeatability.json"
            decision_path = scoring / "decision.json"
            if any(path.exists() for path in (scorecards_path, repeatability_path, decision_path)):
                raise ExpertiseCommandError(
                    "held-out decision evidence already exists; preserve it or create a new evaluation revision"
                )
            final = finalize_heldout(
                run, args.dispositions, args.environment_evidence
            )
            written: list[Path] = []
            try:
                for path, value in (
                    (scorecards_path, final["scorecards"]),
                    (repeatability_path, final["repeatability"]),
                    (decision_path, final["decision"]),
                ):
                    _write_private_new(path, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode(), run)
                    written.append(path)
            except BaseException:
                for path in written:
                    path.unlink(missing_ok=True)
                raise
            decision = final["decision"]
            return _emit(decision, args.json, 0 if decision["state"] == "qualified_disabled" else 3)

        source = Path(args.manifest).expanduser().resolve()
        manifest_bytes = source.read_bytes()
        manifest = json.loads(manifest_bytes)
        validation = validate_fixture_manifest(
            manifest, _corpus_inventory(_framework(repo_root(), args.framework_dir))
        )
        if validation["state"] != "valid":
            return _emit(validation, args.json, 3)
        manifest_path, receipt_path = _frozen_paths(run, manifest["split"])
        if manifest_path.exists() or receipt_path.exists():
            raise ExpertiseCommandError(
                f"{manifest['split']} is already frozen; create a new evaluation revision"
            )
        independence_review = None
        source_sha256 = None
        if manifest["split"] == "evaluation-v2":
            selected = _selected_configuration(run)
            if (
                manifest.get("selected_candidate_id") != selected.get("candidate_id")
                or manifest.get("selected_configuration_digest") != selected.get("executable_configuration_digest")
            ):
                raise ExpertiseCommandError(
                    "evaluation-v2 must bind the selected calibration configuration"
                )
            independence_path = getattr(args, "independence_review", None)
            if not independence_path:
                raise ExpertiseCommandError(
                    "evaluation-v2 freeze requires --independence-review"
                )
            independence_review = _v2_independence_review(
                Path(independence_path).expanduser().resolve(), manifest
            )
            source_sha256 = _campaign_source_sha256(repo_root())
        approved_at = datetime.now(timezone.utc).isoformat()
        receipt = build_freeze_receipt(
            manifest, manifest_bytes, _campaign_identity(args.framework_dir),
            approved_digest=args.approved_digest, approved_by=args.approved_by,
            approved_at=approved_at,
            independence_review=independence_review,
            source_sha256=source_sha256,
        )
        _write_private_new(manifest_path, manifest_bytes, run)
        try:
            _write_private_new(
                receipt_path,
                (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode(),
                run,
            )
        except BaseException:
            manifest_path.unlink(missing_ok=True)
            raise
        result = {
            "state": "frozen", "split": manifest["split"],
            "candidate_manifest_digest": receipt["candidate_manifest_digest"],
            "freeze_receipt_digest": receipt["freeze_receipt_digest"],
            "fixture_count": len(manifest["fixtures"]),
        }
        return _emit(result, args.json, 0)
    except (OSError, UnicodeError, json.JSONDecodeError, ExpertiseCommandError, ValueError, TypeError) as error:
        return _emit({"state": "invalid_request", "reason": str(error)}, args.json, 2)


def _emit(result: dict, as_json: bool, code: int) -> int:
    if as_json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(result.get("state", "unknown"))
        for problem in result.get("blocking_checks", result.get("problems", [])):
            print(f"- {problem}")
        if result.get("reason"):
            print(result["reason"])
        if result.get("remedy"):
            print(f"remedy: {result['remedy']}")
    return code


def dispatch(args) -> int:
    if args.expertise_action == "feasibility":
        return feasibility_command(args)
    if args.expertise_action == "fixtures":
        return fixture_validate_command(args) if args.fixtures_action == "validate" else fixture_independence_command(args)
    if args.expertise_action == "model":
        return model_command(args)
    if args.expertise_action == "index":
        return index_command(args)
    if args.expertise_action == "query":
        return query_command(args)
    if args.expertise_action == "brief":
        return brief_command(args)
    if args.expertise_action == "disposition":
        return disposition_command(args)
    if args.expertise_action == "feedback":
        return feedback_command(args)
    if args.expertise_action == "campaign":
        return campaign_command(args)
    return receipts_command(args)
