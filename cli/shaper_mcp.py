"""Private stdio MCP entry point for a single configured Flow project."""

from __future__ import annotations

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from shaper_gateway import current_state, run_evidence, submit_charter


def configured_root() -> Path:
    value = os.environ.get("FLOW_MCP_PROJECT_ROOT")
    if not value:
        raise RuntimeError("FLOW_MCP_PROJECT_ROOT must be set to a Flow project")
    return Path(value)


mcp = FastMCP("Flow Shaper")


@mcp.tool()
def flow_current_state(limit: int = 20) -> dict:
    """Read bounded current Flow run states; no execution or approval."""
    return current_state(configured_root(), limit)


@mcp.tool()
def flow_run_evidence(work_id: str, artifact: str) -> dict:
    """Read one allowlisted, bounded Flow run artifact by exact name."""
    return run_evidence(configured_root(), work_id, artifact)


@mcp.tool()
def flow_submit_shaper_charter(goal: str, outcomes: str, constraints: str,
                              execution_envelope: str) -> dict:
    """Submit a proposed Shaper charter to Flow's definition lane; requires later approval."""
    return submit_charter(configured_root(), goal=goal, outcomes=outcomes,
                          constraints=constraints, execution_envelope=execution_envelope)


if __name__ == "__main__":
    mcp.run(transport="stdio")
