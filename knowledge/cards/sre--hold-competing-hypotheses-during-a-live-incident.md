---
title: "Hold competing hypotheses during a live incident"
type: "note"
permalink: "cards/sre--hold-competing-hypotheses-during-a-live-incident"
card_id: "flow:entry/sre/hold-competing-hypotheses-during-a-live-incident"
role: "sre"
layer: "baseline"
source_file: "sre.jsonld"
created: "2020-01-01T00:00:00Z"
modified: "2020-01-01T00:00:00Z"
---

# Hold competing hypotheses during a live incident

## Principle

fast pattern matching is right most of the time and wrong in exactly the cases that become incidents. Awareness of that does not correct it; a required pause at a fixed point does.

## Use when

designing incident response, or advising on an active incident where a cause has been proposed and mitigation is about to begin.

## Required behavior

before committing to a mitigation, require at least one named alternative explanation and the observation that would separate it from the current one. Record which observation was taken and what it ruled out.

## Avoid

mitigating on the first familiar signature, and treating a mitigation that appeared to work as confirmation of the diagnosis behind it.

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
    "flow:locator": "cognitive forcing strategies and the diagnostic time-out"
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
    "@id": "flow:entry/sre/hold-competing-hypotheses-during-a-live-incident",
    "@type": "LearningResource",
    "name": "Hold competing hypotheses during a live incident",
    "audience": {
      "@type": "Audience",
      "audienceType": "sre"
    },
    "flow:layer": "baseline",
    "abstract": "fast pattern matching is right most of the time and wrong in exactly the cases that become incidents. Awareness of that does not correct it; a required pause at a fixed point does.",
    "flow:trigger": "designing incident response, or advising on an active incident where a cause has been proposed and mitigation is about to begin.",
    "flow:requiredBehavior": "before committing to a mitigation, require at least one named alternative explanation and the observation that would separate it from the current one. Record which observation was taken and what it ruled out.",
    "flow:failureMode": "mitigating on the first familiar signature, and treating a mitigation that appeared to work as confirmation of the diagnosis behind it.",
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
        "flow:locator": "cognitive forcing strategies and the diagnostic time-out"
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
