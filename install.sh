#!/usr/bin/env bash
# One-time legacy migration and fresh installation: published v2 releases only.
set -euo pipefail
FLOW_INSTALL_REPOSITORY="${FLOW_RELEASE_REPOSITORY:-andyconley/flow}"
FLOW_INSTALL_PYTHON="${FLOW_V2_PYTHON:-python3.12}"
FLOW_INSTALL_TAG="$($FLOW_INSTALL_PYTHON - "$FLOW_INSTALL_REPOSITORY" <<'PYTHON'
import json,re,sys,urllib.request
repo=sys.argv[1]
if not re.fullmatch(r"[\w.-]+/[\w.-]+",repo):raise SystemExit("Invalid repository")
req=urllib.request.Request("https://api.github.com/repos/"+repo+"/releases/latest",headers={"User-Agent":"Flow-v2-bootstrap"})
with urllib.request.urlopen(req,timeout=30) as response:release=json.load(response)
tag=release["tag_name"]
if release.get("draft") or release.get("prerelease") or not re.fullmatch(r"v\d+\.\d+\.\d+",tag):raise SystemExit("Published stable release required")
print(tag)
PYTHON
)"
FLOW_INSTALL_TEMP="$(mktemp -d -t flow-v2-install-XXXXXX)"
trap '"$FLOW_INSTALL_PYTHON" -c "import shutil,sys;shutil.rmtree(sys.argv[1])" "$FLOW_INSTALL_TEMP"' EXIT
git clone --quiet --depth 1 --branch "$FLOW_INSTALL_TAG" "https://github.com/$FLOW_INSTALL_REPOSITORY.git" "$FLOW_INSTALL_TEMP/source"
FLOW_V2_PYTHON="$FLOW_INSTALL_PYTHON" bash "$FLOW_INSTALL_TEMP/source/install-flow.sh" install --repository "$FLOW_INSTALL_REPOSITORY" --version "$FLOW_INSTALL_TAG" "$@"
