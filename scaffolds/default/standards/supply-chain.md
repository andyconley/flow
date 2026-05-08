# Supply Chain Standard

This standard defines how build integrity, dependency hygiene, and artifact trust are managed.

## Principles

- know what is in the software you ship
- know how the artifact was built
- know whether the dependencies you use are still safe and supported

## Dependency hygiene

Projects should:

- maintain dependency update automation
- scan dependencies for known vulnerabilities
- track exceptions explicitly when risk is accepted

## SBOM and artifact inventory

Projects should be able to produce a software bill of materials for shipped artifacts.

Useful outputs include:

- dependency inventory
- vulnerability matching inputs
- auditable release metadata

Common SBOM standards include SPDX and CycloneDX.

## Build provenance and signing

Prefer delivery systems that support:

- signed artifacts
- verifiable provenance
- traceable build identity

Defaults:

- `DO` sign release artifacts when the toolchain supports it
- `DO` keep provenance attached to the artifact or release metadata

## Provenance and integrity models

Useful supply-chain frameworks include:

- SLSA for build integrity maturity
- Sigstore / cosign for signing
- in-toto for pipeline attestation

## Repository health

Projects should maintain:

- protected branches
- required review
- active CI
- secret scanning
- explicit release and versioning discipline

## Dependency update policy

- automate routine updates where practical
- group updates thoughtfully to reduce review noise
- do not let stale dependency debt grow invisibly

## Relevant standards and tools

Common tools:

- syft / trivy / osv-scanner / grype
- cosign
- in-toto
- OpenSSF Scorecard
- Renovate
