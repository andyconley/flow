#!/usr/bin/env bash
set -euo pipefail
FLOW_RELEASE_SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$FLOW_RELEASE_SOURCE/v2${PYTHONPATH:+:$PYTHONPATH}"
exec "${FLOW_V2_PYTHON:-python3.12}" -m poc.managed "${@:-install}"
