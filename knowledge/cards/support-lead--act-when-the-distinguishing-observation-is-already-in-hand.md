---
title: "Act when the distinguishing observation is already in hand"
type: "note"
permalink: "cards/support-lead--act-when-the-distinguishing-observation-is-already-in-hand"
card_id: "flow:entry/support-lead/act-when-the-distinguishing-observation-is-already-in-hand"
role: "support-lead"
layer: "baseline"
source_file: "support-lead.jsonld"
created: "2020-01-01T00:00:00Z"
modified: "2020-01-01T00:00:00Z"
---

# Act when the distinguishing observation is already in hand

## Principle

fast pattern matching is correct most of the time and is what makes routine work affordable. The skill is recognizing the conditions under which it is unreliable, not overriding it everywhere. Deliberate analysis applied to a settled question is a cost paid by the reporter.

## Use when

a known issue or prior case matches, and the observation that would distinguish this report from it has already been taken — by tier 1, by an internal reproduction, by an attached artifact, or by the timeline as reported.

## Required behavior

cite that observation, act on it, and state the one signal that would reopen the case. Weigh remaining investigation against the stakes of the report: an unresolved question worth carrying on an at-risk account is not automatically worth carrying on a single seat.

## Avoid

re-requesting evidence the record already contains, or holding a hypothesis open that the recorded evidence has closed, which spends the reporter's time to restate a conclusion already reached.

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
    "flow:locator": "dual-process reasoning"
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
    "@id": "flow:entry/support-lead/act-when-the-distinguishing-observation-is-already-in-hand",
    "@type": "LearningResource",
    "name": "Act when the distinguishing observation is already in hand",
    "audience": {
      "@type": "Audience",
      "audienceType": "support-lead"
    },
    "flow:layer": "baseline",
    "abstract": "fast pattern matching is correct most of the time and is what makes routine work affordable. The skill is recognizing the conditions under which it is unreliable, not overriding it everywhere. Deliberate analysis applied to a settled question is a cost paid by the reporter.",
    "flow:trigger": "a known issue or prior case matches, and the observation that would distinguish this report from it has already been taken — by tier 1, by an internal reproduction, by an attached artifact, or by the timeline as reported.",
    "flow:requiredBehavior": "cite that observation, act on it, and state the one signal that would reopen the case. Weigh remaining investigation against the stakes of the report: an unresolved question worth carrying on an at-risk account is not automatically worth carrying on a single seat.",
    "flow:failureMode": "re-requesting evidence the record already contains, or holding a hypothesis open that the recorded evidence has closed, which spends the reporter's time to restate a conclusion already reached.",
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
        "flow:locator": "dual-process reasoning"
      }
    ],
    "teaches": [
      {
        "@type": "DefinedTerm",
        "@id": "flow:competency/recognize-when-the-discriminating-evidence-is-already-in-hand",
        "name": "Recognize when the discriminating evidence is already in hand"
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
