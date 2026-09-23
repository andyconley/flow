"""Atomic Flow-owned transition from approved intent to delivery authority."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterator

from delivery_contracts import build_delivery_charter, build_shaper_contract, canonical, digest
from fsutil import ensure_dir, write_atomic


class DeliveryControlError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@contextmanager
def run_lock(run_dir: Path) -> Iterator[None]:
    ensure_dir(run_dir)
    path = run_dir / ".delivery.lock"
    fd = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


@contextmanager
def delivery_authority_guard(run_dir: Path, envelope: dict[str, Any]) -> Iterator[None]:
    """Hold the run claim stable while a v7 caller mutates or dispatches."""
    with run_lock(run_dir):
        run_path = run_dir / "run.json"
        if not run_path.is_file() or run_path.is_symlink():
            raise DeliveryControlError("delivery run authority is unavailable")
        current = json.loads(run_path.read_text())
        delivery = current.get("delivery")
        claim = envelope.get("delivery_lead_claim")
        if (not isinstance(delivery, dict) or not isinstance(claim, dict)
                or delivery.get("owner_status") != "active"
                or delivery.get("owner_generation") != claim.get("generation")
                or delivery.get("lead_claim_digest") != envelope.get("delivery_lead_claim_digest")
                or delivery.get("charter_digest") != envelope.get("delivery_charter_digest")):
            raise DeliveryControlError("delivery owner generation is stale")
        yield


def _safe_source(root: Path, work_id: str, relative: str) -> Path:
    path = root / relative
    if not relative.startswith(f".flow/runs/{work_id}/") or not path.resolve().is_relative_to(root.resolve()):
        raise DeliveryControlError(f"source path is outside the current run: {relative}")
    if not path.is_file() or path.is_symlink():
        raise DeliveryControlError(f"approved source is unavailable: {relative}")
    return path


def _source_snapshot(root: Path, work_id: str, artifacts: dict[str, str]) -> dict[str, dict[str, str]]:
    required = {"requirements", "acceptance_criteria", "shaper_intent"}
    missing = sorted(required - set(artifacts))
    if missing:
        raise DeliveryControlError("approved run is missing artifacts: " + ", ".join(missing))
    selected = {key: artifacts[key] for key in ("requirements", "acceptance_criteria", "shaper_intent", "solution", "orchestration_manifest") if artifacts.get(key)}
    snapshots: dict[str, dict[str, str]] = {}
    for key, relative in selected.items():
        if not isinstance(relative, str):
            raise DeliveryControlError(f"approved source path is invalid: {key}")
        path = _safe_source(root, work_id, relative)
        snapshots[key] = {"path": relative, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return snapshots


def _event_exists(events: Path, event: dict[str, Any]) -> bool:
    if not events.exists():
        return False
    for line in events.read_text().splitlines():
        if not line.strip():
            continue
        try:
            existing = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            existing.get("event") == event.get("event")
            and existing.get("delivery_charter_digest") == event.get("delivery_charter_digest")
            and existing.get("owner_generation") == event.get("owner_generation")
        ):
            return True
    return False


def _append_event(events: Path, event: dict[str, Any]) -> None:
    # A repeated append is prevented by the authority digest. A crash before
    # this append is recoverable: replay sees run.json and reconciles it.
    if _event_exists(events, event):
        return
    ensure_dir(events.parent)
    with events.open("a") as handle:
        handle.write(canonical(event) + "\n")


def _write_immutable(path: Path, payload: dict[str, Any]) -> None:
    content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text() != content:
            raise DeliveryControlError(f"immutable artifact conflict: {path.name}")
        return
    write_atomic(path, content)


def start_plan(work_id: str, *, root: Path, expected_updated_at: str | None = None, failure_point: str | None = None) -> tuple[bool, dict[str, Any], list[str]]:
    """Seal delivery authority. ``run.json`` is the only authority commit point."""
    root, run_dir = root.resolve(), (root / ".flow" / "runs" / work_id)
    run_path, events_path = run_dir / "run.json", run_dir / "events.jsonl"
    if not run_path.is_file():
        return False, {}, ["run not found"]
    with run_lock(run_dir):
        try:
            current = json.loads(run_path.read_text())
            if expected_updated_at is not None and current.get("updated_at") != expected_updated_at:
                return False, current, ["stale run revision"]
            state = current.get("state")
            snapshots = _source_snapshot(root, work_id, current.get("artifacts", {}))
            approved_digests = current.get("approved_artifact_digests", {})
            for name, source in snapshots.items():
                if approved_digests.get(name) != source["sha256"]:
                    return False, current, [f"approved {name} changed after approval"]
            if state == "planning" and current.get("delivery"):
                delivery = current["delivery"]
                if delivery.get("source_digests") != snapshots:
                    return False, current, ["approved source bytes changed after delivery authority was sealed"]
                _append_event(events_path, {
                    "at": current.get("updated_at"), "event": "start-plan", "from": state,
                    "to": state, "delivery_charter_digest": delivery["charter_digest"],
                    "owner_generation": delivery["owner_generation"], "reconciled": True,
                })
                return True, current, []
            if state not in {"definition_approved", "solution_approved"}:
                return False, current, [f"invalid transition: start-plan requires definition_approved or solution_approved; current state is {state or '<new>'}"]

            intent_path = _safe_source(root, work_id, snapshots["shaper_intent"]["path"])
            try:
                approved_intent = json.loads(intent_path.read_text())
            except json.JSONDecodeError as exc:
                raise DeliveryControlError("approved Shaper intent is invalid JSON") from exc
            shaper = build_shaper_contract(work_id, snapshots, approved_intent)
            charter = build_delivery_charter(shaper)
            handoff = {
                "schema_version": 1, "kind": "definition_to_delivery_handoff", "run_id": work_id,
                "shaper_contract_id": shaper["shaper_contract_id"], "shaper_contract_digest": shaper["digest"],
                "delivery_charter_id": charter["charter_id"], "delivery_charter_digest": charter["digest"],
                "source_digests": snapshots, "transition": "start-plan",
            }
            handoff["digest"] = digest(handoff)
            attempt_id = f"logical-{charter['digest'][:20]}"
            claim = {
                "schema_version": 1, "kind": "delivery_lead_claim", "logical_delivery_attempt_id": attempt_id,
                "owner": "delivery-lead", "generation": 1, "status": "active", "charter_digest": charter["digest"],
                "supersedes": None,
            }
            claim["digest"] = digest(claim)
            if failure_point == "before-staging":
                raise OSError("injected failure before staging")
            # Staging is keyed by the authority digest. A crashed, unreferenced
            # stage can never conflict with a later source-corrected retry.
            delivery_dir = run_dir / "delivery" / charter["digest"]
            _write_immutable(delivery_dir / "shaper-contract.json", shaper)
            _write_immutable(delivery_dir / "delivery-charter.json", charter)
            _write_immutable(delivery_dir / "handoff.json", handoff)
            _write_immutable(delivery_dir / "lead-claim.json", claim)
            if failure_point == "after-staging":
                raise OSError("injected failure after staging")
            now = _now()
            next_run = dict(current)
            next_run.update({"state": "planning", "lane": "plan", "phase": "planning", "updated_at": now, "last_event": "start-plan"})
            next_run["gates"] = dict(current.get("gates", {}), **{"start-plan": now})
            next_run["delivery"] = {
                "shaper_contract_id": shaper["shaper_contract_id"], "shaper_contract_digest": shaper["digest"],
                "charter_id": charter["charter_id"], "charter_digest": charter["digest"], "handoff_digest": handoff["digest"],
                "logical_delivery_attempt_id": attempt_id, "lead_claim_digest": claim["digest"], "owner_generation": 1,
                "owner_status": "active", "delivery_artifact_dir": f"delivery/{charter['digest']}",
                "lead_claim_path": f"delivery/{charter['digest']}/lead-claim.json", "source_digests": snapshots,
            }
            if failure_point == "before-run-replace":
                raise OSError("injected failure before authority commit")
            write_atomic(run_path, json.dumps(next_run, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
            if failure_point == "after-run-replace":
                return True, next_run, []
            _append_event(events_path, {
                "at": now, "event": "start-plan", "from": state, "to": "planning",
                "delivery_charter_digest": charter["digest"], "handoff_digest": handoff["digest"],
                "logical_delivery_attempt_id": attempt_id, "owner_generation": 1,
            })
            if failure_point == "after-event-append":
                raise OSError("injected failure after event append")
            return True, next_run, []
        except (DeliveryControlError, ValueError, OSError) as exc:
            return False, json.loads(run_path.read_text()), [str(exc)]


def change_lead_claim(
    work_id: str,
    action: str,
    *,
    root: Path,
    owner: str | None = None,
    expected_generation: int | None = None,
) -> tuple[bool, dict[str, Any], list[str]]:
    """Apply an explicit, generation-fenced Delivery Lead recovery action.

    This is intentionally separate from generic lifecycle pause/resume.  A
    lifecycle transition cannot silently change the actor allowed to dispatch.
    """
    if action not in {"attention", "release", "resume", "supersede"}:
        return False, {}, ["unknown lead action"]
    root, run_dir = root.resolve(), (root / ".flow" / "runs" / work_id)
    run_path = run_dir / "run.json"
    if not run_path.is_file():
        return False, {}, ["run not found"]
    with run_lock(run_dir):
        current = json.loads(run_path.read_text())
        delivery = current.get("delivery")
        if not isinstance(delivery, dict):
            return False, current, ["delivery authority is not sealed"]
        generation = delivery.get("owner_generation")
        if not isinstance(generation, int) or generation < 1:
            return False, current, ["delivery owner generation is invalid"]
        if expected_generation is not None and expected_generation != generation:
            return False, current, ["stale delivery owner generation"]
        if action in {"resume", "supersede"} and current.get("pending_unknown_actions"):
            return False, current, ["unknown action blocks Delivery Lead successor"]
        status = delivery.get("owner_status")
        if action == "attention":
            if status != "active":
                return False, current, ["only an active Delivery Lead can require attention"]
            next_generation, next_status = generation, "attention_required"
        elif action == "release":
            if status not in {"active", "attention_required"}:
                return False, current, ["only an active or attention-required Delivery Lead can release"]
            next_generation, next_status = generation, "released"
        else:
            if status not in {"attention_required", "released", "active"}:
                return False, current, ["Delivery Lead cannot be resumed or superseded from its current status"]
            if not owner or not owner.strip():
                return False, current, ["resume or supersede requires an explicit owner identity"]
            next_generation, next_status = generation + 1, "active"
        previous_relative = delivery.get("lead_claim_path")
        if not isinstance(previous_relative, str) or not previous_relative.startswith("delivery/"):
            return False, current, ["current Delivery Lead claim path is invalid"]
        previous_claim = run_dir / previous_relative
        if not previous_claim.is_file():
            return False, current, ["current Delivery Lead claim is unavailable"]
        claim = {
            "schema_version": 1, "kind": "delivery_lead_claim",
            "logical_delivery_attempt_id": delivery["logical_delivery_attempt_id"],
            "owner": owner.strip() if action in {"resume", "supersede"} else json.loads(previous_claim.read_text())["owner"],
            "generation": next_generation, "status": next_status,
            "charter_digest": delivery["charter_digest"],
            "supersedes": delivery["lead_claim_digest"],
        }
        claim["digest"] = digest(claim)
        claim_name = f"lead-claim-g{next_generation}-{next_status}.json"
        claim_relative = f"{previous_relative.rsplit('/', 1)[0]}/{claim_name}"
        _write_immutable(run_dir / claim_relative, claim)
        now = _now()
        next_run = dict(current)
        next_delivery = dict(delivery)
        next_delivery.update({
            "lead_claim_digest": claim["digest"], "owner_generation": next_generation,
            "owner_status": next_status, "lead_claim_path": claim_relative,
        })
        next_run["delivery"] = next_delivery
        next_run["updated_at"] = now
        write_atomic(run_path, json.dumps(next_run, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        _append_event(run_dir / "events.jsonl", {
            "at": now, "event": f"delivery-lead-{action}", "from": status, "to": next_status,
            "delivery_charter_digest": delivery["charter_digest"], "owner_generation": next_generation,
        })
        return True, next_run, []
