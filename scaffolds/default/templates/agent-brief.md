# Agent Brief: [assignment id]

## Identity and outcome

- Work id:
- Lane:
- Role/provider:
- Stable provider identity (`human`, `agent`, or `external_provider`):
- Required outcome:

## Evidence inventory

- Existing artifacts and paths:
- Known gaps:
- Claim statuses expected:

## Scope and capabilities

- Read scopes:
- Write scopes, or explicit read-only status:
- Required capabilities and observed status (`confirmed`, `missing`, `unknown`):
- Coordination mode and group:
- Other workers active in the same area:

## Output contract

- Output path:
- Format:
- Observable success criteria:
- Prohibited actions:
- Host-owned evidence: never create or edit `verification.json` or captured logs;
  return ordinary test results and identities for host capture after execution.
- Approved criteria and verification-plan references/digests:
- Registered evaluator inputs; changing them requires explicit review:
- Failed check and failure evidence (for repairs):
- Remaining repair allowance (two allocations per check across sessions):

## Handback

- Report changed paths, evidence, claims, uncertainties, and conflicts.
- Do not convert `unknown` or `unverified` into certainty.
