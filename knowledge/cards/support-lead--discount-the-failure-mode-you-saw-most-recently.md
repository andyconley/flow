---
title: "Discount the failure mode you saw most recently"
type: "note"
permalink: "cards/support-lead--discount-the-failure-mode-you-saw-most-recently"
card_id: "flow:entry/support-lead/discount-the-failure-mode-you-saw-most-recently"
role: "support-lead"
layer: "baseline"
source_file: "support-lead.jsonld"
created: "2020-01-01T00:00:00Z"
modified: "2020-01-01T00:00:00Z"
---

# Discount the failure mode you saw most recently

## Principle

the causes that come to mind fastest are the ones seen most recently, not the ones most likely here. Recent volume crowds out rare failures that present the same way.

## Use when

the symptom matches a pattern from a recent incident, release, or cluster of tickets.

## Required behavior

state the recent case you are matching against and the observation that distinguishes this report from it. Take that observation before acting on the match.

## Avoid

applying the current known-issue workaround to a report that merely resembles it, which buries a distinct defect inside a resolved one.

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
    "flow:locator": "availability"
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
    "@id": "flow:entry/support-lead/discount-the-failure-mode-you-saw-most-recently",
    "@type": "LearningResource",
    "name": "Discount the failure mode you saw most recently",
    "audience": {
      "@type": "Audience",
      "audienceType": "support-lead"
    },
    "flow:layer": "baseline",
    "abstract": "the causes that come to mind fastest are the ones seen most recently, not the ones most likely here. Recent volume crowds out rare failures that present the same way.",
    "flow:trigger": "the symptom matches a pattern from a recent incident, release, or cluster of tickets.",
    "flow:requiredBehavior": "state the recent case you are matching against and the observation that distinguishes this report from it. Take that observation before acting on the match.",
    "flow:failureMode": "applying the current known-issue workaround to a report that merely resembles it, which buries a distinct defect inside a resolved one.",
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
        "flow:locator": "availability"
      }
    ],
    "teaches": [
      {
        "@type": "DefinedTerm",
        "@id": "flow:competency/test-a-familiar-pattern-match-before-acting-on-it",
        "name": "Test a familiar pattern match before acting on it"
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
