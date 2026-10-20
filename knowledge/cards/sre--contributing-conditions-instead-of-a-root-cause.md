---
title: "Contributing conditions instead of a root cause"
type: "note"
permalink: "cards/sre--contributing-conditions-instead-of-a-root-cause"
card_id: "flow:entry/sre/contributing-conditions-instead-of-a-root-cause"
role: "sre"
layer: "baseline"
source_file: "sre.jsonld"
created: "2020-01-01T00:00:00Z"
modified: "2020-01-01T00:00:00Z"
---

# Contributing conditions instead of a root cause

## Principle

consequential failure needs several conditions to line up at once, so naming one of them as the cause is a choice about where to stop looking. The narrower the causal story, the narrower the defenses built from it.

## Use when

reviewing an incident, a near miss, or a failure that a change is meant to prevent.

## Required behavior

list the conditions that had to hold together, and for each one say which defense was supposed to catch it and why it did not. Include the detection gap as a finding in its own right, separate from the trigger.

## Avoid

writing a single-cause account, or listing conditions and then promoting one of them to "the" cause in the summary line.

## Sources

[
  {
    "citation": {
      "@type": "Book",
      "author": "Richard I. Cook",
      "name": "How Complex Systems Fail",
      "datePublished": "1998",
      "version": "rev. 2002",
      "@id": "flow:work/cook-how-complex-systems-fail"
    },
    "flow:locator": "theses 3, 7, and 15"
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
    "@id": "flow:entry/sre/contributing-conditions-instead-of-a-root-cause",
    "@type": "LearningResource",
    "name": "Contributing conditions instead of a root cause",
    "audience": {
      "@type": "Audience",
      "audienceType": "sre"
    },
    "flow:layer": "baseline",
    "abstract": "consequential failure needs several conditions to line up at once, so naming one of them as the cause is a choice about where to stop looking. The narrower the causal story, the narrower the defenses built from it.",
    "flow:trigger": "reviewing an incident, a near miss, or a failure that a change is meant to prevent.",
    "flow:requiredBehavior": "list the conditions that had to hold together, and for each one say which defense was supposed to catch it and why it did not. Include the detection gap as a finding in its own right, separate from the trigger.",
    "flow:failureMode": "writing a single-cause account, or listing conditions and then promoting one of them to \"the\" cause in the summary line.",
    "flow:source": [
      {
        "citation": {
          "@type": "Book",
          "author": "Richard I. Cook",
          "name": "How Complex Systems Fail",
          "datePublished": "1998",
          "version": "rev. 2002",
          "@id": "flow:work/cook-how-complex-systems-fail"
        },
        "flow:locator": "theses 3, 7, and 15"
      }
    ],
    "teaches": [
      {
        "@type": "DefinedTerm",
        "@id": "flow:competency/distinguish-contributing-conditions-from-a-named-cause",
        "name": "Distinguish contributing conditions from a named cause"
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
