---
title: "Plan in proportion to risk"
type: "note"
permalink: "cards/lead-developer--plan-in-proportion-to-risk"
card_id: "flow:entry/lead-developer/plan-in-proportion-to-risk"
role: "lead-developer"
layer: "baseline"
source_file: "lead-developer.jsonld"
created: "2020-01-01T00:00:00Z"
modified: "2020-01-01T00:00:00Z"
---

# Plan in proportion to risk

## Principle

planning effort belongs where reversibility, blast radius, or missing proof makes change risky.

## Use when

choosing plan depth for an approved implementation change.

## Required behavior

classify reversibility, blast radius, and coverage before selecting a concise short plan or the full planning format.

## Avoid

inventing slices and generic risks for a local reversible covered change.

## Sources

[
  {
    "citation": {
      "@type": "Book",
      "author": "George Fairbanks",
      "name": "Just Enough Software Architecture",
      "@id": "flow:work/fairbanks-just-enough-architecture"
    },
    "flow:locator": "risk-driven design"
  },
  {
    "citation": {
      "@type": "Book",
      "author": "Jez Humble and David Farley",
      "name": "Continuous Delivery",
      "sameAs": "https://martinfowler.com/books/continuousDelivery.html",
      "@id": "flow:work/humble-farley-continuous-delivery"
    },
    "flow:locator": "small safe increments and reliable release"
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
    "@id": "flow:entry/lead-developer/plan-in-proportion-to-risk",
    "@type": "LearningResource",
    "name": "Plan in proportion to risk",
    "audience": {
      "@type": "Audience",
      "audienceType": "lead-developer"
    },
    "flow:layer": "baseline",
    "abstract": "planning effort belongs where reversibility, blast radius, or missing proof makes change risky.",
    "flow:trigger": "choosing plan depth for an approved implementation change.",
    "flow:requiredBehavior": "classify reversibility, blast radius, and coverage before selecting a concise short plan or the full planning format.",
    "flow:failureMode": "inventing slices and generic risks for a local reversible covered change.",
    "flow:source": [
      {
        "citation": {
          "@type": "Book",
          "author": "George Fairbanks",
          "name": "Just Enough Software Architecture",
          "@id": "flow:work/fairbanks-just-enough-architecture"
        },
        "flow:locator": "risk-driven design"
      },
      {
        "citation": {
          "@type": "Book",
          "author": "Jez Humble and David Farley",
          "name": "Continuous Delivery",
          "sameAs": "https://martinfowler.com/books/continuousDelivery.html",
          "@id": "flow:work/humble-farley-continuous-delivery"
        },
        "flow:locator": "small safe increments and reliable release"
      }
    ],
    "teaches": [
      {
        "@type": "DefinedTerm",
        "@id": "flow:competency/plan-in-proportion-to-risk",
        "name": "Plan in proportion to risk"
      }
    ],
    "flow:lifecycle": {
      "state": "current",
      "owner": "flow:owner/framework-maintainers",
      "attestedAt": "2026-09-11T00:00:00Z",
      "evidence": [
        {
          "kind": "review-record",
          "ref": "docs/evidence/three-role-expertise-expansion/README.md"
        }
      ],
      "supersedes": []
    }
  }
}
```
