---
title: "Carry hypothesis and fact separately across a handoff"
type: "note"
permalink: "cards/support-lead--carry-hypothesis-and-fact-separately-across-a-handoff"
card_id: "flow:entry/support-lead/carry-hypothesis-and-fact-separately-across-a-handoff"
role: "support-lead"
layer: "baseline"
source_file: "support-lead.jsonld"
created: "2020-01-01T00:00:00Z"
modified: "2020-01-01T00:00:00Z"
---

# Carry hypothesis and fact separately across a handoff

## Principle

a label survives a handoff better than the doubt attached to it. The next person receives the hypothesis as a finding and investigates from there instead of from the evidence.

## Use when

escalating, reassigning, or writing up an unresolved case.

## Required behavior

the escalation packet states what was observed, what was reproduced and under what conditions, what is currently believed and on what basis, what was ruled out and by which observation, and what is still open. A belief never appears without its basis.

## Avoid

leading the packet with a suspected cause, or dropping ruled-out leads so the next person repeats them.

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
    "flow:locator": "diagnosis momentum"
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
    "@id": "flow:entry/support-lead/carry-hypothesis-and-fact-separately-across-a-handoff",
    "@type": "LearningResource",
    "name": "Carry hypothesis and fact separately across a handoff",
    "audience": {
      "@type": "Audience",
      "audienceType": "support-lead"
    },
    "flow:layer": "baseline",
    "abstract": "a label survives a handoff better than the doubt attached to it. The next person receives the hypothesis as a finding and investigates from there instead of from the evidence.",
    "flow:trigger": "escalating, reassigning, or writing up an unresolved case.",
    "flow:requiredBehavior": "the escalation packet states what was observed, what was reproduced and under what conditions, what is currently believed and on what basis, what was ruled out and by which observation, and what is still open. A belief never appears without its basis.",
    "flow:failureMode": "leading the packet with a suspected cause, or dropping ruled-out leads so the next person repeats them.",
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
        "flow:locator": "diagnosis momentum"
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
