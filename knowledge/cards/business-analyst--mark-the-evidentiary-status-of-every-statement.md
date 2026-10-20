---
title: "Mark the evidentiary status of every statement"
type: "note"
permalink: "cards/business-analyst--mark-the-evidentiary-status-of-every-statement"
card_id: "flow:entry/business-analyst/mark-the-evidentiary-status-of-every-statement"
role: "business-analyst"
layer: "baseline"
source_file: "business-analyst.jsonld"
created: "2020-01-01T00:00:00Z"
modified: "2020-01-01T00:00:00Z"
---

# Mark the evidentiary status of every statement

## Principle

a label attached early travels downstream as established fact. Each handoff inherits it without the qualification it carried when it was written.

## Use when

writing any definition, problem statement, or requirement that another role will act on.

## Required behavior

label each statement as observed, inferred, assumed, or decided, and keep the four visibly separate in the artifact. An assumption carries what would confirm or refute it.

## Avoid

writing an inference in the declarative voice of an observation, which is how an assumption becomes a constraint nobody remembers agreeing to.

## Sources

[
  {
    "citation": {
      "@type": "ScholarlyArticle",
      "author": "Pat Croskerry",
      "name": "From Mindless to Mindful Practice — Cognitive Bias and Clinical Decision Making",
      "isPartOf": "New England Journal of Medicine",
      "datePublished": "2013",
      "pagination": "2445-2448",
      "sameAs": "https://doi.org/10.1056/NEJMp1303712",
      "@id": "flow:work/croskerry-mindless-to-mindful"
    },
    "flow:locator": "the diagnosis-momentum effect"
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
    "@id": "flow:entry/business-analyst/mark-the-evidentiary-status-of-every-statement",
    "@type": "LearningResource",
    "name": "Mark the evidentiary status of every statement",
    "audience": {
      "@type": "Audience",
      "audienceType": "business-analyst"
    },
    "flow:layer": "baseline",
    "abstract": "a label attached early travels downstream as established fact. Each handoff inherits it without the qualification it carried when it was written.",
    "flow:trigger": "writing any definition, problem statement, or requirement that another role will act on.",
    "flow:requiredBehavior": "label each statement as observed, inferred, assumed, or decided, and keep the four visibly separate in the artifact. An assumption carries what would confirm or refute it.",
    "flow:failureMode": "writing an inference in the declarative voice of an observation, which is how an assumption becomes a constraint nobody remembers agreeing to.",
    "flow:source": [
      {
        "citation": {
          "@type": "ScholarlyArticle",
          "author": "Pat Croskerry",
          "name": "From Mindless to Mindful Practice — Cognitive Bias and Clinical Decision Making",
          "isPartOf": "New England Journal of Medicine",
          "datePublished": "2013",
          "pagination": "2445-2448",
          "sameAs": "https://doi.org/10.1056/NEJMp1303712",
          "@id": "flow:work/croskerry-mindless-to-mindful"
        },
        "flow:locator": "the diagnosis-momentum effect"
      }
    ],
    "teaches": [
      {
        "@type": "DefinedTerm",
        "@id": "flow:competency/separate-observation-interpretation-assumption-and-decision",
        "name": "Separate observation, interpretation, assumption, and decision"
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
