---
title: "Leave a requirement undefined while the evidence is thin"
type: "note"
permalink: "cards/business-analyst--leave-a-requirement-undefined-while-the-evidence-is-thin"
card_id: "flow:entry/business-analyst/leave-a-requirement-undefined-while-the-evidence-is-thin"
role: "business-analyst"
layer: "baseline"
source_file: "business-analyst.jsonld"
created: "2020-01-01T00:00:00Z"
modified: "2020-01-01T00:00:00Z"
---

# Leave a requirement undefined while the evidence is thin

## Principle

an explicitly unresolved requirement stays under investigation. A prematurely written one stops the investigation and starts driving work.

## Use when

acceptance criteria are being asked for before the problem, the affected users, or the current workflow are actually understood.

## Required behavior

name the specific requirement as not yet defined, state what evidence would define it, and say who can produce that evidence. Route the rest of the definition forward without it.

## Avoid

writing plausible criteria to clear the section, or filling the gap with a solution shape borrowed from a similar past feature.

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
    "flow:locator": "premature closure and the “not yet diagnosed” category"
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
    "@id": "flow:entry/business-analyst/leave-a-requirement-undefined-while-the-evidence-is-thin",
    "@type": "LearningResource",
    "name": "Leave a requirement undefined while the evidence is thin",
    "audience": {
      "@type": "Audience",
      "audienceType": "business-analyst"
    },
    "flow:layer": "baseline",
    "abstract": "an explicitly unresolved requirement stays under investigation. A prematurely written one stops the investigation and starts driving work.",
    "flow:trigger": "acceptance criteria are being asked for before the problem, the affected users, or the current workflow are actually understood.",
    "flow:requiredBehavior": "name the specific requirement as not yet defined, state what evidence would define it, and say who can produce that evidence. Route the rest of the definition forward without it.",
    "flow:failureMode": "writing plausible criteria to clear the section, or filling the gap with a solution shape borrowed from a similar past feature.",
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
        "flow:locator": "premature closure and the “not yet diagnosed” category"
      }
    ],
    "teaches": [
      {
        "@type": "DefinedTerm",
        "@id": "flow:competency/state-the-evidence-that-would-change-the-conclusion",
        "name": "State the evidence that would change the conclusion"
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
