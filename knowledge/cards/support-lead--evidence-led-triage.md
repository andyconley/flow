---
title: "Evidence-led triage"
type: "note"
permalink: "cards/support-lead--evidence-led-triage"
card_id: "flow:entry/support-lead/evidence-led-triage"
role: "support-lead"
layer: "baseline"
source_file: "support-lead.jsonld"
created: "2020-01-01T00:00:00Z"
modified: "2020-01-01T00:00:00Z"
---

# Evidence-led triage

## Principle

a plausible explanation is not evidence. The first cause that fits suppresses the search for a better one, and stopping at plausible is the common way a triage conclusion turns out wrong.

## Use when

a report is incomplete, intermittent, or admits more than one cause.

## Required behavior

record symptom, timeline, environment, observed evidence, live hypotheses, tests run, and remaining uncertainty as separate items. Keep at least one alternative alive until an observation rules it out.

## Avoid

converting the first familiar symptom pattern into a root-cause claim.

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
    "flow:locator": "anchoring and premature closure"
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
    "@id": "flow:entry/support-lead/evidence-led-triage",
    "@type": "LearningResource",
    "name": "Evidence-led triage",
    "audience": {
      "@type": "Audience",
      "audienceType": "support-lead"
    },
    "flow:layer": "baseline",
    "abstract": "a plausible explanation is not evidence. The first cause that fits suppresses the search for a better one, and stopping at plausible is the common way a triage conclusion turns out wrong.",
    "flow:trigger": "a report is incomplete, intermittent, or admits more than one cause.",
    "flow:requiredBehavior": "record symptom, timeline, environment, observed evidence, live hypotheses, tests run, and remaining uncertainty as separate items. Keep at least one alternative alive until an observation rules it out.",
    "flow:failureMode": "converting the first familiar symptom pattern into a root-cause claim.",
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
        "flow:locator": "anchoring and premature closure"
      }
    ],
    "teaches": [
      {
        "@type": "DefinedTerm",
        "@id": "flow:competency/preserve-competing-hypotheses-until-evidence-rules-them-out",
        "name": "Preserve competing hypotheses until evidence rules them out"
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
