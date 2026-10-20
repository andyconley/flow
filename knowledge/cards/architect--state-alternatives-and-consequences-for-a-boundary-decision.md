---
title: "State alternatives and consequences for a boundary decision"
type: "note"
permalink: "cards/architect--state-alternatives-and-consequences-for-a-boundary-decision"
card_id: "flow:entry/architect/state-alternatives-and-consequences-for-a-boundary-decision"
role: "architect"
layer: "baseline"
source_file: "architect.jsonld"
created: "2020-01-01T00:00:00Z"
modified: "2020-01-01T00:00:00Z"
---

# State alternatives and consequences for a boundary decision

## Principle

a durable technical choice needs its context, the alternatives considered, the tradeoffs accepted, and the consequences that follow. The record preserves why the boundary exists when circumstances later change.

## Use when

a change crosses a module, interface, persistence, compatibility, or other durable system boundary with more than one viable option.

## Required behavior

state the decision, context, viable alternatives, tradeoffs, consequences, and the condition that would justify revisiting it. Keep product priority and file-level task sequencing with their owning roles.

## Avoid

calling a local refactor an architecture decision, or recording a chosen option without the forces and consequences that make it reviewable.

## Sources

[
  {
    "citation": {
      "@type": "Article",
      "author": "Martin Fowler",
      "name": "Architecture Decision Record",
      "datePublished": "2026",
      "sameAs": "https://martinfowler.com/bliki/ArchitectureDecisionRecord.html",
      "@id": "flow:work/fowler-architecture-decision-record"
    },
    "flow:locator": "decision, context, trade-offs, and consequences"
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
    "@id": "flow:entry/architect/state-alternatives-and-consequences-for-a-boundary-decision",
    "@type": "LearningResource",
    "name": "State alternatives and consequences for a boundary decision",
    "audience": {
      "@type": "Audience",
      "audienceType": "architect"
    },
    "flow:layer": "baseline",
    "abstract": "a durable technical choice needs its context, the alternatives considered, the tradeoffs accepted, and the consequences that follow. The record preserves why the boundary exists when circumstances later change.",
    "flow:trigger": "a change crosses a module, interface, persistence, compatibility, or other durable system boundary with more than one viable option.",
    "flow:requiredBehavior": "state the decision, context, viable alternatives, tradeoffs, consequences, and the condition that would justify revisiting it. Keep product priority and file-level task sequencing with their owning roles.",
    "flow:failureMode": "calling a local refactor an architecture decision, or recording a chosen option without the forces and consequences that make it reviewable.",
    "flow:source": [
      {
        "citation": {
          "@type": "Article",
          "author": "Martin Fowler",
          "name": "Architecture Decision Record",
          "datePublished": "2026",
          "sameAs": "https://martinfowler.com/bliki/ArchitectureDecisionRecord.html",
          "@id": "flow:work/fowler-architecture-decision-record"
        },
        "flow:locator": "decision, context, trade-offs, and consequences"
      }
    ],
    "teaches": [
      {
        "@type": "DefinedTerm",
        "@id": "flow:competency/state-alternatives-and-consequences-for-a-boundary-decision",
        "name": "State alternatives and consequences for a boundary decision"
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
