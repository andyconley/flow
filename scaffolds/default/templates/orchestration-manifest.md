# Orchestration Manifest Template

Author `.flow/runs/<work-id>/orchestration.json` as JSON. Remove the explanatory placeholders; JSON comments are not allowed.

```json
{
  "schema_version": 1,
  "work_id": "<work-id>",
  "mode": "delegated",
  "risk": {
    "hard_triggers": [],
    "aggravating_factors": [],
    "classification": "standard",
    "rationale": "<why the controlled triggers apply>"
  },
  "assignments": [
    {
      "id": "implementation",
      "lane": "implement",
      "role": "lead-developer",
      "provider": {"kind": "agent", "id": "<stable-provider-id>"},
      "brief_path": ".flow/runs/<work-id>/briefs/implementation.md",
      "input_evidence": [".flow/runs/<work-id>/requirements.md"],
      "read_scopes": ["cli"],
      "write_scopes": ["cli"],
      "read_only": false,
      "required_capabilities": [{"name": "filesystem-write", "status": "confirmed"}],
      "output": {"path": "cli/example.py", "format": "python"},
      "success_criteria": ["targeted tests pass"],
      "claim_statuses": ["observed", "inferred", "recommended", "unverified"],
      "coordination": {"mode": "serialized", "group": "implementation"}
    }
  ],
  "shared_state": [],
  "reconciliation": {
    "artifact_path": ".flow/runs/<work-id>/findings-reconciliation.md",
    "status": "resolved",
    "claims": []
  },
  "verification": {
    "producer_assignments": ["implementation"],
    "evidence_collector_assignment": "implementation",
    "verifier_assignment": "implementation",
    "independent": false,
    "artifact_path": ".flow/runs/<work-id>/review.md"
  }
}
```

See `standards/orchestration.md` for controlled values and stage rules.
