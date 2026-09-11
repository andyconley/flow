# Architecture evidence pilot

This is an isolated, local-only pilot for reviewing structural and selected-function quality evidence. It is not a `flow` command, production gate, CI integration, or proof that a reviewer will make better decisions.

The pilot reads a pinned source tree, writes immutable evidence directories, and renders a report intended for `file://`. It never fetches tools, runs analysis from the viewer, or changes policy approval.

## Environment

Use the pilot lock only on macOS arm64 with Python 3.14. `scripts/architecture_evidence/requirements.lock` pins Tach 0.35.0, Radon 6.0.1, coverage.py 7.14.0, and mutmut 3.7.0 with their resolved dependencies. Regenerate and verify a separate lock before using another platform or Python version.

The supplied fixture config names absolute executables under `/private/tmp/flow-architecture-tools`. Treat those as examples of a prebuilt isolated environment, not portable paths. Configure the absolute `tach_executable` and quality `python_executable` for the environment that owns the run.

## Evidence flow

Run from the isolated checkout. Outputs must be new paths; the pilot rejects existing output files and directories.

```text
python3 scripts/architecture_evidence_pilot.py collect --source SOURCE --config CONFIG --out BASELINE
python3 scripts/architecture_evidence_pilot.py collect --source CANDIDATE --config CONFIG --out CANDIDATE_SNAPSHOT
python3 scripts/architecture_evidence_pilot.py compare --baseline BASELINE --candidate CANDIDATE_SNAPSHOT --policy POLICY --out PACKET
python3 scripts/architecture_evidence_pilot.py render --packet PACKET --out architecture-report.html
python3 scripts/architecture_evidence_pilot.py verify --packet PACKET --candidate CANDIDATE --report architecture-report.html
```

`collect` inventories configured source roots, copies source excerpts, runs the configured adapter(s) in disposable workspaces, and records raw artifacts, versions, hashes, and gaps. The Python graph adapter treats Tach map output as graph authority and nonraw per-module reports as source-line authority. A missing source join is a required gap.

`compare` validates both snapshots, calculates the direct-import delta and new cycles, verifies the policy receipt, and produces a candidate-bound packet. Policy results and overall evidence results are distinct: a policy failure can remain visible while missing required evidence makes the overall result inconclusive.

`render` validates a packet, embeds the data and pinned Cytoscape asset into one HTML file, and emits a receipt that binds packet, report, manifest, and viewer bytes. `verify` rechecks that receipt and the candidate source identity. A failing policy packet may render and verify successfully; neither operation accepts a code change.

Exit codes are `0` for a completed valid operation or policy pass, `1` for a proven compare policy failure, `2` for invalid invocation, and `3` for inconclusive evidence or an infrastructure failure.

## Policy receipt

The policy file defines only direct-import rules. A sibling `policy-approval.json` is required for a conclusive policy result. Its current creation is a manual run-host step: it records the policy digest, exact approved rules, approver, the approved plan text and its digest, and the `approve-plan` event copied from the run event artifact. It also names the plan and event files used for those values.

`compare` copies those referenced files into the packet and rejects a mismatch between file contents and the receipt. Do not regenerate a policy receipt merely to make a changed rule pass; policy, scope, exclusions, or approval changes require a new engineering decision.

## Report behavior

The report offers baseline, candidate, and delta views, component and text filters, keyboard zoom/pan controls, graph selection, source drilldown, quality details, and an equivalent keyboard-accessible evidence list. It also exposes findings, evidence gaps, baseline/new cycles, inventory counts, and unsupported tool capabilities as text. Removed nodes remain in delta view and read their source/quality evidence from the baseline snapshot. A graph-only packet explicitly says its required quality evidence is disabled and is not a full-pilot pass.

Before embedding data, the renderer removes raw artifact paths, executable configuration, full approval plan/event text, and approval source-file paths. The report retains only the identity, graph/source, quality, capability, result, and approval-digest fields needed for review. Displayed labels and excerpts use text nodes, and the restrictive CSP permits no network connection.

An excerpt that exceeds its line or byte limit is visibly incomplete. It is not evidence of complete drilldown. The viewer reports evidence states; it contains no approval or mutation controls.

## Required follow-through

Run the documented browser check manually in a supported local browser after opening the rendered file through `file://`. The available browser automation cannot validate this URL mode. Verify keyboard controls, all view/filter/detail states, offline behavior, and hostile source display before claiming browser acceptance.

The four matched human review exercise and its expand/revise/defer decision remain pending. A passing automated command sequence does not complete the pilot.

## Validation status and test scope

The selected-function coverage record explicitly labels its supplemental behavioral harness. The existing 64 collector tests run separately as baseline compatibility proof; the displayed coverage is not whole-suite coverage. Mutation records distinguish original input bytes from the instrumented source and include an actual executed import-path receipt.

For optional real-tool integration tests set `FLOW_ARCHITECTURE_PYTHON` to the pinned environment interpreter. Without that variable, unit tests still run and the external-tool integration case is skipped. The example config contains placeholder executable paths; copy it outside the checkout and replace them before collecting.

The local browser automation tool rejected file-URL navigation under its security policy. No alternate browser route was attempted. Offline interaction, keyboard behavior and the four timed reviews therefore require manual evidence before pilot acceptance. Source/unit checks and CLI integrity checks do not substitute for those observations.
