---
title: "Ask for the last occurrence, not a description"
type: "note"
permalink: "cards/support-lead--ask-for-the-last-occurrence-not-a-description"
card_id: "flow:entry/support-lead/ask-for-the-last-occurrence-not-a-description"
role: "support-lead"
layer: "baseline"
source_file: "support-lead.jsonld"
created: "2020-01-01T00:00:00Z"
modified: "2020-01-01T00:00:00Z"
---

# Ask for the last occurrence, not a description

## Principle

reporters summarize and interpret before they reach you. The specific most recent instance is recallable in detail; the general account of it has already been smoothed into a theory.

## Use when

taking a report, or clarifying one that arrives as a conclusion ("the sync is broken", "it's slow for everyone").

## Required behavior

ask for the last time it happened, what they were doing immediately before, what they saw, and what they did next. Prefer open prompts over yes-or-no confirmations of your own theory, and let a pause run rather than filling it.

## Avoid

asking whether a suspected condition was present, which supplies the answer and contaminates the only account you have.

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
    "@id": "flow:entry/support-lead/ask-for-the-last-occurrence-not-a-description",
    "@type": "LearningResource",
    "name": "Ask for the last occurrence, not a description",
    "audience": {
      "@type": "Audience",
      "audienceType": "support-lead"
    },
    "flow:layer": "baseline",
    "abstract": "reporters summarize and interpret before they reach you. The specific most recent instance is recallable in detail; the general account of it has already been smoothed into a theory.",
    "flow:trigger": "taking a report, or clarifying one that arrives as a conclusion (\"the sync is broken\", \"it's slow for everyone\").",
    "flow:requiredBehavior": "ask for the last time it happened, what they were doing immediately before, what they saw, and what they did next. Prefer open prompts over yes-or-no confirmations of your own theory, and let a pause run rather than filling it.",
    "flow:failureMode": "asking whether a suspected condition was present, which supplies the answer and contaminates the only account you have.",
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
