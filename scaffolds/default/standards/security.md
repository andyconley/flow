# Security Standard

This standard defines baseline security expectations across design, implementation, delivery, and operations.

## Shift-left security

Security is not a final review phase. It should be part of:

- design
- local development
- code review
- CI
- runtime operations

## Secure defaults

- least privilege for identities and permissions
- validate all external input
- protect secrets and sensitive data
- make risky behavior visible in code review and CI

## Input validation

- `DO` validate user, webhook, and API inputs with explicit schemas
- `DO` sanitize data rendered into user-facing surfaces
- `DO NOT` trust raw external payloads
- `DO NOT` use dynamic code execution on untrusted input

## Secrets management

- secrets should live in dedicated secret-management systems or encrypted secret stores
- secrets should never be committed to source control
- secrets should never be logged
- secret rotation should be part of the operating model, not an afterthought

## Identity and authorization

- user-initiated flows should respect user permissions
- machine-to-machine access should use workload or service identity where possible
- authorization decisions belong close to the domain that understands the access rules

## Security automation

Projects should run appropriate automated checks in CI, such as:

- static analysis
- dependency vulnerability scans
- secret scanning
- container or artifact scanning
- infrastructure-as-code scanning when applicable

## Secure review checklist

Security-sensitive changes should be reviewed for:

- permission or scope expansion
- secrets exposure risk
- unsafe logging
- trust-boundary violations
- misuse of machine vs user identity
- missing validation on new external inputs

## Security governance

- significant security tradeoffs should be documented
- accepted risks should be explicit and owned
- projects should map their security posture to a recognized framework when appropriate, such as OWASP ASVS or NIST CSF
