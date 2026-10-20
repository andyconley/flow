---
title: "Postmortem output is a change to conditions"
type: "note"
permalink: "cards/sre--postmortem-output-is-a-change-to-conditions"
card_id: "flow:entry/sre/postmortem-output-is-a-change-to-conditions"
role: "sre"
layer: "baseline"
source_file: "sre.jsonld"
created: "2020-01-01T00:00:00Z"
modified: "2020-01-01T00:00:00Z"
---

# Postmortem output is a change to conditions

## Principle

the surface narrative names a person and an action; the explanatory account names the tools, signals, procedures, and staffing that made the action reasonable. Only the second kind produces something to change.

## Use when

producing findings or actions from any incident review.

## Required behavior

every action item names a condition — a signal, a tool, a default, a procedure, a staffing or timing constraint — and the change to it. An action whose object is a person's future attentiveness is not an action.

## Avoid

adopting blameless language while the outcome is still a lesson delivered to an individual, which teaches the team to withhold detail.

## Sources

[
  {
    "citation": {
      "@type": "Article",
      "author": "John Allspaw",
      "name": "Blameless PostMortems and a Just Culture",
      "isPartOf": "Etsy Code as Craft",
      "datePublished": "2012",
      "sameAs": "https://www.etsy.com/codeascraft/blameless-postmortems-and-a-just-culture/",
      "@id": "flow:work/allspaw-blameless-postmortems"
    },
    "flow:locator": "first and second stories"
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
    "@id": "flow:entry/sre/postmortem-output-is-a-change-to-conditions",
    "@type": "LearningResource",
    "name": "Postmortem output is a change to conditions",
    "audience": {
      "@type": "Audience",
      "audienceType": "sre"
    },
    "flow:layer": "baseline",
    "abstract": "the surface narrative names a person and an action; the explanatory account names the tools, signals, procedures, and staffing that made the action reasonable. Only the second kind produces something to change.",
    "flow:trigger": "producing findings or actions from any incident review.",
    "flow:requiredBehavior": "every action item names a condition — a signal, a tool, a default, a procedure, a staffing or timing constraint — and the change to it. An action whose object is a person's future attentiveness is not an action.",
    "flow:failureMode": "adopting blameless language while the outcome is still a lesson delivered to an individual, which teaches the team to withhold detail.",
    "flow:source": [
      {
        "citation": {
          "@type": "Article",
          "author": "John Allspaw",
          "name": "Blameless PostMortems and a Just Culture",
          "isPartOf": "Etsy Code as Craft",
          "datePublished": "2012",
          "sameAs": "https://www.etsy.com/codeascraft/blameless-postmortems-and-a-just-culture/",
          "@id": "flow:work/allspaw-blameless-postmortems"
        },
        "flow:locator": "first and second stories"
      }
    ],
    "teaches": [
      {
        "@type": "DefinedTerm",
        "@id": "flow:competency/direct-corrective-action-at-conditions-rather-than-at-individuals",
        "name": "Direct corrective action at conditions rather than at individuals"
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
