---
title: "Elicit past behavior, not stated intent"
type: "note"
permalink: "cards/business-analyst--elicit-past-behavior-not-stated-intent"
card_id: "flow:entry/business-analyst/elicit-past-behavior-not-stated-intent"
role: "business-analyst"
layer: "baseline"
source_file: "business-analyst.jsonld"
created: "2020-01-01T00:00:00Z"
modified: "2020-01-01T00:00:00Z"
---

# Elicit past behavior, not stated intent

## Principle

people describe what they have already done far more reliably than what they would do. Questions about a hypothetical product return social responses, not information.

## Use when

gathering requirements from a stakeholder, customer, operator, or internal advocate.

## Required behavior

ask for specific past instances — the last time this happened, what they did, what it cost them, what they tried first. Record the instance, not the generalization drawn from it. When enthusiasm arrives in place of an instance, redirect to the most recent occurrence.

## Avoid

treating agreement, interest, or a stated willingness to use something as evidence that the requirement is real.

## Sources

[
  {
    "citation": {
      "@type": "Book",
      "author": "Rob Fitzpatrick",
      "name": "The Mom Test",
      "datePublished": "2013",
      "@id": "flow:work/fitzpatrick-the-mom-test"
    },
    "flow:locator": "chapter 1"
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
    "@id": "flow:entry/business-analyst/elicit-past-behavior-not-stated-intent",
    "@type": "LearningResource",
    "name": "Elicit past behavior, not stated intent",
    "audience": {
      "@type": "Audience",
      "audienceType": "business-analyst"
    },
    "flow:layer": "baseline",
    "abstract": "people describe what they have already done far more reliably than what they would do. Questions about a hypothetical product return social responses, not information.",
    "flow:trigger": "gathering requirements from a stakeholder, customer, operator, or internal advocate.",
    "flow:requiredBehavior": "ask for specific past instances — the last time this happened, what they did, what it cost them, what they tried first. Record the instance, not the generalization drawn from it. When enthusiasm arrives in place of an instance, redirect to the most recent occurrence.",
    "flow:failureMode": "treating agreement, interest, or a stated willingness to use something as evidence that the requirement is real.",
    "flow:source": [
      {
        "citation": {
          "@type": "Book",
          "author": "Rob Fitzpatrick",
          "name": "The Mom Test",
          "datePublished": "2013",
          "@id": "flow:work/fitzpatrick-the-mom-test"
        },
        "flow:locator": "chapter 1"
      }
    ],
    "teaches": [
      {
        "@type": "DefinedTerm",
        "@id": "flow:competency/ask-non-leading-questions",
        "name": "Ask non-leading questions"
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
