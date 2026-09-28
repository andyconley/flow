# Documentation review: managed MAF runtime readiness

## Scope

Reviewed the operator-facing README and CLI reference, `install-flow.sh`, ADR
0020, runtime lock/requirements naming, and generated Flow help surfaces against
AC14 (documentation/help/release proof) and the findings in
`research/quality-review.md`. No provider or network call was used.

## Findings

### Correct and aligned

- `README.md` exposes `flow runtime readiness`, `flow runtime install-maf`, and
  the `recover-runtime-startup` successor command.
- `docs/adr/0020-managed-maf-runtime-readiness.md` records the managed pointer,
  digest-addressed environments, explicit override, pre-attempt boundary,
  warning-versus-strict diagnostic posture, and historical receipt compatibility.
- `scaffolds/default/commands/flow-help.md` describes all three runtime commands
  and includes `maf` in the smoke target. The generated help validation should
  remain part of release proof.
- `install-flow.sh` invokes `runtime install-maf` after the base launcher smoke
  and restores source/config/runtime selection on failure, matching the staged
  installation contract.

### Documentation corrected in this slice

`docs/cli-reference.md` previously described a manual `requirements.txt` plus
`FLOW_MAF_PYTHON` setup as the normal path. That guidance was stale after the
managed runtime implementation and could cause operators to bypass the managed
pointer. It now documents `runtime install-maf` as the normal path, treats
`FLOW_MAF_PYTHON` as an explicit validated compatibility override, points at
the resolved lock, and explains the strict readiness/smoke versus ordinary
doctor warning behavior and zero-side-effect refusal.

### Remaining release/acceptance blockers

These are implementation or validation blockers, not wording gaps, and must not
be hidden by documentation:

- The quality review reported false-positive readiness when distribution metadata
  exists but required modules are not importable. AC1/AC2/AC10/AC15 require a
  real import and child milestone before a runtime is selected or a delivery
  attempt can proceed.
- Managed provisioning must exercise the digest-addressed environment without
  `FLOW_MAF_PYTHON`, and release validation must prove a clean isolated-home
  install, real imports, strict readiness, and hermetic child smoke.
- Develop conversion/update rollback, provisioning locking/concurrency,
  artifact-integrity identity, exact startup-failure classification, and the
  first-upgrade bridge remain implementation evidence gaps called out by the
  quality review.
- The resolved inventory is deterministic, but the current evidence records no
  wheel hashes. AC15 should either add supported-platform artifact hashes and
  hash-enforced installation or explicitly document the supported-platform
  boundary and its integrity limitation.

## Generated/runtime surface check

The canonical generated help source already contains the new runtime commands;
after any `flow.toml` or scaffold change, run the generated-help check and both
adapter `--check` commands. Do not hand-edit generated Claude/Codex files as a
substitute for updating the scaffold/source manifest.

## Verdict

Documentation is aligned after the CLI-reference correction, but AC14 and
handback remain blocked until the quality-review implementation findings are
closed and their evidence is recorded in validation results. This review does
not claim release readiness or live-provider readiness.
