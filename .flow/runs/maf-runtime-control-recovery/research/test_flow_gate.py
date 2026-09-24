"""Focused boundary tests for the Flow-owned dispatch ledger."""

from __future__ import annotations

import tempfile
from pathlib import Path

import flow_gate
from flow_gate import FlowGate


def request(number: int, **overrides):
    result = {"request_id": f"r-{number}", "kind": "delegate", "role": "test-engineer", "provider": "ollama", "hard_cap_usd": 0.0}
    result.update(overrides)
    return result


def fresh() -> FlowGate:
    directory = Path(tempfile.mkdtemp(prefix="flow-gate-test-"))
    return FlowGate(directory / "ledger.sqlite")


def main() -> None:
    gate = fresh()
    assert gate.decide(request(1)).allowed
    assert not gate.decide(request(1)).allowed
    assert gate.claim_dispatch("r-1")
    assert not gate.claim_dispatch("r-1")
    assert gate.complete("r-1", "worker output")
    assert not gate.claim_dispatch("r-1")

    gate = fresh()
    assert gate.decide(request(1)).allowed
    assert gate.decide(request(2)).allowed
    assert gate.decide(request(3)).allowed
    assert gate.decide(request(4)).reason == "concurrency_cap"

    gate = fresh()
    for n in range(6):
        assert gate.decide(request(n)).allowed
        assert gate.claim_dispatch(f"r-{n}")
        gate.complete(f"r-{n}", "done")
    assert gate.decide(request(6)).reason == "delegation_cap"

    gate = fresh()
    assert gate.decide(request(1, kind="replan")).allowed
    assert not gate.claim_dispatch("r-1")
    gate.complete_replan("r-1")
    assert gate.decide(request(2, kind="replan")).allowed
    gate.complete_replan("r-2")
    assert gate.decide(request(3, kind="replan")).reason == "replan_cap"

    gate = fresh()
    assert gate.decide(request(1, role="security-reviewer")).reason == "specialist_denied"
    assert gate.decide(request(2, provider="codex", hard_cap_usd=None)).reason == "provider_without_enforceable_cap"
    assert gate.decide(request(3, provider="claude", hard_cap_usd=3)).reason == "provider_without_enforceable_cap"
    assert gate.decide(request(4, provider="metered-test", hard_cap_usd=6)).reason == "paid_cap_unverified"
    assert gate.decide(request(5, provider="metered-test", hard_cap_usd=6, cap_enforced_by_adapter=True)).allowed
    assert gate.decide(request(6, provider="metered-test", hard_cap_usd=5, cap_enforced_by_adapter=True)).reason == "paid_budget_cap"
    assert not gate.claim_dispatch("r-5")  # Test-only adapter cannot dispatch.
    assert gate.decide(request(7, hard_cap_usd=float("nan"))).reason == "invalid_hard_cap"

    # Mutation check: breaking the concurrency cap must trip its covering assertion.
    original = flow_gate.MAX_CONCURRENT
    try:
        flow_gate.MAX_CONCURRENT = 4
        gate = fresh()
        for n in range(3):
            assert gate.decide(request(n)).allowed
        caught = False
        try:
            assert gate.decide(request(4)).reason == "concurrency_cap"
        except AssertionError:
            caught = True
        assert caught
    finally:
        flow_gate.MAX_CONCURRENT = original
    print("flow gate tests passed; concurrency mutation caught")


if __name__ == "__main__":
    main()
