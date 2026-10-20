---
title: "Premortem a change before it rolls"
type: "note"
permalink: "cards/sre--premortem-a-change-before-it-rolls"
card_id: "flow:entry/sre/premortem-a-change-before-it-rolls"
role: "sre"
layer: "baseline"
source_file: "sre.jsonld"
created: "2020-01-01T00:00:00Z"
modified: "2020-01-01T00:00:00Z"
---

# Premortem a change before it rolls

## Principle

imagining the rollout as already failed retrieves concrete scenarios that a forward-looking risk review does not reach, and it makes raising an objection the assigned task rather than an act of dissent.

## Use when

a migration, cutover, schema change, or high-blast-radius rollout is about to be scheduled.

## Required behavior

pose it as done and broken — this rolled out as planned and took the service down — collect causes before evaluating any, then map the survivors onto rollback triggers, guardrail metrics, and the staging of the rollout.

## Avoid

substituting a generic risk list, or letting the loudest scenario displace the quieter ones before all are captured.

## Sources

[
  {
    "citation": {
      "@type": "Article",
      "author": "Gary Klein",
      "name": "Performing a Project Premortem",
      "isPartOf": "Harvard Business Review",
      "datePublished": "2007",
      "@id": "flow:work/klein-project-premortem"
    }
  }
]

## Complete authored card (lossless)

```json
{
  "@context": {
    "@vocab": "https://schema.org/",
    "flow": "https://andyconley.github.io/flow/ns#",
    "teaches": {
      "@id": "https://schema.org/teaches",
      "@type": "@id"
    }
  },
  "card": {
    "@id": "flow:entry/sre/premortem-a-change-before-it-rolls",
    "@type": "LearningResource",
    "name": "Premortem a change before it rolls",
    "audience": {
      "@type": "Audience",
      "audienceType": "sre"
    },
    "flow:layer": "baseline",
    "abstract": "imagining the rollout as already failed retrieves concrete scenarios that a forward-looking risk review does not reach, and it makes raising an objection the assigned task rather than an act of dissent.",
    "flow:trigger": "a migration, cutover, schema change, or high-blast-radius rollout is about to be scheduled.",
    "flow:requiredBehavior": "pose it as done and broken — this rolled out as planned and took the service down — collect causes before evaluating any, then map the survivors onto rollback triggers, guardrail metrics, and the staging of the rollout.",
    "flow:failureMode": "substituting a generic risk list, or letting the loudest scenario displace the quieter ones before all are captured.",
    "flow:source": [
      {
        "citation": {
          "@type": "Article",
          "author": "Gary Klein",
          "name": "Performing a Project Premortem",
          "isPartOf": "Harvard Business Review",
          "datePublished": "2007",
          "@id": "flow:work/klein-project-premortem"
        }
      }
    ],
    "teaches": [
      {
        "@type": "DefinedTerm",
        "@id": "flow:competency/surface-dissent-by-treating-failure-as-already-accomplished",
        "name": "Surface dissent by treating failure as already accomplished"
      }
    ],
    "flow:lifecycle": {
      "state": "current",
      "owner": "flow:owner/framework-maintainers",
      "attestedAt": "2026-09-11T00:00:00Z",
      "evidence": [
        {
          "kind": "review-record",
          "ref": "docs/evidence/agent-expertise-expansion/README.md"
        }
      ],
      "supersedes": []
    }
  }
}
```
