---
title: "Do not read the user's actions as obvious errors"
type: "note"
permalink: "cards/support-lead--do-not-read-the-user-s-actions-as-obvious-errors"
card_id: "flow:entry/support-lead/do-not-read-the-user-s-actions-as-obvious-errors"
role: "support-lead"
layer: "baseline"
source_file: "support-lead.jsonld"
created: "2020-01-01T00:00:00Z"
modified: "2020-01-01T00:00:00Z"
---

# Do not read the user's actions as obvious errors

## Principle

knowing the outcome makes the correct path look plain, and the user's choice look careless. What they did made sense given what the product was showing them at the time.

## Use when

the report involves a user action that contributed to the problem, including a misconfiguration or a skipped step.

## Required behavior

describe what the interface, docs, or defaults afforded at that moment, and record the mismatch as a product finding routed to discovery. Guidance to the user is separate from the finding, and does not substitute for it.

## Avoid

closing a case as user error, which discards the signal and teaches the reporter to supply less detail next time.

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
    "@id": "flow:entry/support-lead/do-not-read-the-user-s-actions-as-obvious-errors",
    "@type": "LearningResource",
    "name": "Do not read the user's actions as obvious errors",
    "audience": {
      "@type": "Audience",
      "audienceType": "support-lead"
    },
    "flow:layer": "baseline",
    "abstract": "knowing the outcome makes the correct path look plain, and the user's choice look careless. What they did made sense given what the product was showing them at the time.",
    "flow:trigger": "the report involves a user action that contributed to the problem, including a misconfiguration or a skipped step.",
    "flow:requiredBehavior": "describe what the interface, docs, or defaults afforded at that moment, and record the mismatch as a product finding routed to discovery. Guidance to the user is separate from the finding, and does not substitute for it.",
    "flow:failureMode": "closing a case as user error, which discards the signal and teaches the reporter to supply less detail next time.",
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
