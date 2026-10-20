---
title: "Reframe a product request as the job behind it"
type: "note"
permalink: "cards/business-analyst--reframe-a-product-request-as-the-job-behind-it"
card_id: "flow:entry/business-analyst/reframe-a-product-request-as-the-job-behind-it"
role: "business-analyst"
layer: "baseline"
source_file: "business-analyst.jsonld"
created: "2020-01-01T00:00:00Z"
modified: "2020-01-01T00:00:00Z"
---

# Reframe a product request as the job behind it

## Principle

a request phrased as a thing to build has already chosen a solution. The unit worth analyzing is what the requester is trying to accomplish, which usually survives longer than the artifact they named.

## Use when

the incoming request names a feature, screen, field, or system rather than an outcome or a difficulty.

## Required behavior

state the request as given, then state the underlying job and who holds it. Where the two diverge, say what the divergence would change about scope. Carry both forward — do not discard the original wording.

## Avoid

accepting the named artifact as the requirement, or silently substituting your own reframing for what the requester actually asked.

## Sources

[
  {
    "citation": {
      "@type": "Article",
      "author": "Theodore Levitt",
      "name": "Marketing Myopia",
      "isPartOf": "Harvard Business Review",
      "datePublished": "1960",
      "@id": "flow:work/levitt-marketing-myopia"
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
    "@id": "flow:entry/business-analyst/reframe-a-product-request-as-the-job-behind-it",
    "@type": "LearningResource",
    "name": "Reframe a product request as the job behind it",
    "audience": {
      "@type": "Audience",
      "audienceType": "business-analyst"
    },
    "flow:layer": "baseline",
    "abstract": "a request phrased as a thing to build has already chosen a solution. The unit worth analyzing is what the requester is trying to accomplish, which usually survives longer than the artifact they named.",
    "flow:trigger": "the incoming request names a feature, screen, field, or system rather than an outcome or a difficulty.",
    "flow:requiredBehavior": "state the request as given, then state the underlying job and who holds it. Where the two diverge, say what the divergence would change about scope. Carry both forward — do not discard the original wording.",
    "flow:failureMode": "accepting the named artifact as the requirement, or silently substituting your own reframing for what the requester actually asked.",
    "flow:source": [
      {
        "citation": {
          "@type": "Article",
          "author": "Theodore Levitt",
          "name": "Marketing Myopia",
          "isPartOf": "Harvard Business Review",
          "datePublished": "1960",
          "@id": "flow:work/levitt-marketing-myopia"
        }
      }
    ],
    "teaches": [
      {
        "@type": "DefinedTerm",
        "@id": "flow:competency/restate-a-solution-shaped-request-as-the-outcome-behind-it",
        "name": "Restate a solution-shaped request as the outcome behind it"
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
