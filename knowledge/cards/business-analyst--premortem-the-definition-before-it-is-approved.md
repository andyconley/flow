---
title: "Premortem the definition before it is approved"
type: "note"
permalink: "cards/business-analyst--premortem-the-definition-before-it-is-approved"
card_id: "flow:entry/business-analyst/premortem-the-definition-before-it-is-approved"
role: "business-analyst"
layer: "baseline"
source_file: "business-analyst.jsonld"
created: "2020-01-01T00:00:00Z"
modified: "2020-01-01T00:00:00Z"
---

# Premortem the definition before it is approved

## Principle

imagining a failure that has already happened surfaces concrete causes that forward-looking risk questions do not reach, and it gives objections a legitimate form.

## Use when

a definition is about to be approved and handed to solutioning or planning.

## Required behavior

pose the failure as accomplished — this was built, it met every criterion here, and the user was not helped — then collect the reasons before evaluating any of them. Fold survivors into non-goals, assumptions, or the evidence that would change the requirement.

## Avoid

replacing the accomplished-failure framing with an abstract "what could go wrong", or filtering the list as it is generated.

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
    "@id": "flow:entry/business-analyst/premortem-the-definition-before-it-is-approved",
    "@type": "LearningResource",
    "name": "Premortem the definition before it is approved",
    "audience": {
      "@type": "Audience",
      "audienceType": "business-analyst"
    },
    "flow:layer": "baseline",
    "abstract": "imagining a failure that has already happened surfaces concrete causes that forward-looking risk questions do not reach, and it gives objections a legitimate form.",
    "flow:trigger": "a definition is about to be approved and handed to solutioning or planning.",
    "flow:requiredBehavior": "pose the failure as accomplished — this was built, it met every criterion here, and the user was not helped — then collect the reasons before evaluating any of them. Fold survivors into non-goals, assumptions, or the evidence that would change the requirement.",
    "flow:failureMode": "replacing the accomplished-failure framing with an abstract \"what could go wrong\", or filtering the list as it is generated.",
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
