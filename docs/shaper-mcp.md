# Flow Shaper MCP bridge

This private bridge gives an ordinary ChatGPT conversation a small view of one
Flow project. Flow remains the system of record. The three tools read current
run state, read one approved run artifact, and submit a **proposed** charter.
Submission starts Flow's `defining` lane. It does not approve requirements,
launch Magentic, grant a worker call, or edit source code.

## Local setup

Use Python 3.12 and install the optional MCP dependency into a dedicated
virtual environment:

```sh
python3.12 -m venv ~/.flow/shaper-mcp-venv
~/.flow/shaper-mcp-venv/bin/python -m pip install -r ~/.flow/source/requirements-shaper-mcp.txt
export FLOW_MCP_PROJECT_ROOT=/Users/andyconley/src/flow
PYTHONPATH=~/.flow/source/cli ~/.flow/shaper-mcp-venv/bin/python ~/.flow/source/cli/shaper_mcp.py
```

The server uses **stdio only**. It does not open a network port. Set
`FLOW_MCP_PROJECT_ROOT` explicitly to the checkout whose `.flow` overlay is
authoritative. The process should run as the local Flow owner. Do not expose
this single-user server as a public unauthenticated HTTP endpoint.

## Connect a normal ChatGPT Chat

Use the [Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)
with a local stdio profile. The tunnel client needs a Platform tunnel ID and
an API key with tunnel permissions. Associate the tunnel with the intended
ChatGPT workspace, enable developer mode, and add the tunnel-backed MCP server
in ChatGPT Plugins. Start a **new ordinary Chat**, enable the connection, and
ask it to read Flow's current state. Then submit a harmless shaping proposal
and verify the returned work ID exists in `.flow/runs/` with state `defining`.

Example profile command (supply your actual tunnel ID through the documented
Platform setup; never place its API key in this repository):

```sh
tunnel-client init --sample sample_mcp_stdio_local \
  --profile flow-shaper --tunnel-id "$FLOW_MCP_TUNNEL_ID" \
  --mcp-command "env FLOW_MCP_PROJECT_ROOT=/Users/andyconley/src/flow PYTHONPATH=$HOME/.flow/source/cli $HOME/.flow/shaper-mcp-venv/bin/python $HOME/.flow/source/cli/shaper_mcp.py"
tunnel-client doctor --profile flow-shaper --explain
tunnel-client run --profile flow-shaper
```

The tunnel authenticates the connection to the configured workspace. This
bridge is single-user and has no separate OAuth user identity; do not promote
it to a shared or public plugin without adding per-user authorization.

## Tool boundaries

- `flow_current_state`: at most 50 non-archived run summaries.
- `flow_run_evidence`: one allowlisted artifact, at most 16 KiB, with exact
  work ID and artifact name; symlinks are rejected.
- `flow_submit_shaper_charter`: bounded goal, outcomes, constraints, and
  execution envelope fields. Flow creates a private `shaper-submission.json`
  and a `start-definition` event. Normal definition approval and execution
  gates remain in force.

Read and write calls through this connection may require separate ChatGPT tool
approval depending on the workspace's plugin settings. A successful MCP call
does not imply that Magentic has run.

The state tool sends each run's `next_action` text, and the evidence tool sends
the selected file's contents to the connected ChatGPT client. The allowlist
limits file names, not sensitivity or approval status. Keep secrets and private
material out of artifacts you expose through this single-user bridge.
