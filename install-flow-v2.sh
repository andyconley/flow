#!/usr/bin/env bash
set -euo pipefail
FLOW_V2_REPOSITORY="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${FLOW_V2_PYTHON:-python3.12}" "$FLOW_V2_REPOSITORY/v2/bootstrap.py" "$@"
