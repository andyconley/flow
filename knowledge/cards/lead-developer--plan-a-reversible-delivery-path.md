---
title: "Plan a reversible delivery path"
type: "note"
permalink: "cards/lead-developer--plan-a-reversible-delivery-path"
card_id: "flow:entry/lead-developer/plan-a-reversible-delivery-path"
role: "lead-developer"
layer: "baseline"
source_file: "lead-developer.jsonld"
created: "2020-01-01T00:00:00Z"
modified: "2020-01-01T00:00:00Z"
---

# Plan a reversible delivery path

## Principle

uncertain work becomes safer when choices can be deferred or reversed after evidence arrives. A delivery plan must make its proof and its rollback boundary visible before the irreversible step.

## Use when

planning implementation of approved work that changes persistence, compatibility, a public interface, or a deployment path.

## Required behavior

sequence small changes so each has a proof point, name the first irreversible step, and state the rollback or recovery action before that boundary. Escalate unresolved product or architecture decisions instead of absorbing them.

## Avoid

presenting a file list as an execution plan while leaving verification, migration, and recovery to an unspecified later step.

## Sources

[
  {
    "citation": {
      "@type": "Article",
      "author": "Martin Fowler",
      "name": "Is Design Dead?",
      "sameAs": "https://martinfowler.com/articles/designDead.html",
      "@id": "flow:work/fowler-is-design-dead"
    },
    "flow:locator": "Reversibility"
  },
  {
    "citation": {
      "@type": "Article",
      "author": "Atlassian",
      "name": "What Is Continuous Deployment?",
      "sameAs": "https://www.atlassian.com/continuous-delivery/software-testing/continuous-deployment",
      "@id": "flow:work/atlassian-continuous-deployment"
    },
    "flow:locator": "rolling deployments and monitoring"
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
    "@id": "flow:entry/lead-developer/plan-a-reversible-delivery-path",
    "@type": "LearningResource",
    "name": "Plan a reversible delivery path",
    "audience": {
      "@type": "Audience",
      "audienceType": "lead-developer"
    },
    "flow:layer": "baseline",
    "abstract": "uncertain work becomes safer when choices can be deferred or reversed after evidence arrives. A delivery plan must make its proof and its rollback boundary visible before the irreversible step.",
    "flow:trigger": "planning implementation of approved work that changes persistence, compatibility, a public interface, or a deployment path.",
    "flow:requiredBehavior": "sequence small changes so each has a proof point, name the first irreversible step, and state the rollback or recovery action before that boundary. Escalate unresolved product or architecture decisions instead of absorbing them.",
    "flow:failureMode": "presenting a file list as an execution plan while leaving verification, migration, and recovery to an unspecified later step.",
    "flow:source": [
      {
        "citation": {
          "@type": "Article",
          "author": "Martin Fowler",
          "name": "Is Design Dead?",
          "sameAs": "https://martinfowler.com/articles/designDead.html",
          "@id": "flow:work/fowler-is-design-dead"
        },
        "flow:locator": "Reversibility"
      },
      {
        "citation": {
          "@type": "Article",
          "author": "Atlassian",
          "name": "What Is Continuous Deployment?",
          "sameAs": "https://www.atlassian.com/continuous-delivery/software-testing/continuous-deployment",
          "@id": "flow:work/atlassian-continuous-deployment"
        },
        "flow:locator": "rolling deployments and monitoring"
      }
    ],
    "teaches": [
      {
        "@type": "DefinedTerm",
        "@id": "flow:competency/plan-a-reversible-delivery-path",
        "name": "Plan a reversible delivery path"
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
