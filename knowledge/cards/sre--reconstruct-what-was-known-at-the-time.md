---
title: "Reconstruct what was known at the time"
type: "note"
permalink: "cards/sre--reconstruct-what-was-known-at-the-time"
card_id: "flow:entry/sre/reconstruct-what-was-known-at-the-time"
role: "sre"
layer: "baseline"
source_file: "sre.jsonld"
created: "2020-01-01T00:00:00Z"
modified: "2020-01-01T00:00:00Z"
---

# Reconstruct what was known at the time

## Principle

once the ending is known the path to it looks obvious, which makes every operator decision along the way look worse than it was. Retroactive obviousness is a finding about the system's signals, not about the operator.

## Use when

any part of the timeline involves a human decision, including a decision to wait or to do nothing.

## Required behavior

for each decision point, record what the operator believed, what the instruments were showing, what other readings were live, and what pressure they were under. Then treat any gap between the signal and the situation as a defect to fix.

## Avoid

phrasing a timeline entry as a failure to notice, escalate, or check — that wording has already assigned blame and closed the question.

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
    "flow:locator": "thesis 8"
  },
  {
    "citation": {
      "@type": "Article",
      "author": "John Allspaw",
      "name": "Blameless PostMortems and a Just Culture",
      "isPartOf": "Etsy Code as Craft",
      "datePublished": "2012",
      "sameAs": "https://www.etsy.com/codeascraft/blameless-postmortems-and-a-just-culture/",
      "@id": "flow:work/allspaw-blameless-postmortems"
    }
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
    "@id": "flow:entry/sre/reconstruct-what-was-known-at-the-time",
    "@type": "LearningResource",
    "name": "Reconstruct what was known at the time",
    "audience": {
      "@type": "Audience",
      "audienceType": "sre"
    },
    "flow:layer": "baseline",
    "abstract": "once the ending is known the path to it looks obvious, which makes every operator decision along the way look worse than it was. Retroactive obviousness is a finding about the system's signals, not about the operator.",
    "flow:trigger": "any part of the timeline involves a human decision, including a decision to wait or to do nothing.",
    "flow:requiredBehavior": "for each decision point, record what the operator believed, what the instruments were showing, what other readings were live, and what pressure they were under. Then treat any gap between the signal and the situation as a defect to fix.",
    "flow:failureMode": "phrasing a timeline entry as a failure to notice, escalate, or check — that wording has already assigned blame and closed the question.",
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
        "flow:locator": "thesis 8"
      },
      {
        "citation": {
          "@type": "Article",
          "author": "John Allspaw",
          "name": "Blameless PostMortems and a Just Culture",
          "isPartOf": "Etsy Code as Craft",
          "datePublished": "2012",
          "sameAs": "https://www.etsy.com/codeascraft/blameless-postmortems-and-a-just-culture/",
          "@id": "flow:work/allspaw-blameless-postmortems"
        }
      }
    ],
    "teaches": [
      {
        "@type": "DefinedTerm",
        "@id": "flow:competency/account-for-hindsight-when-judging-past-decisions",
        "name": "Account for hindsight when judging past decisions"
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
