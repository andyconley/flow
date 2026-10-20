---
title: "State what a mitigation newly makes possible"
type: "note"
permalink: "cards/sre--state-what-a-mitigation-newly-makes-possible"
card_id: "flow:entry/sre/state-what-a-mitigation-newly-makes-possible"
role: "sre"
layer: "baseline"
source_file: "sre.jsonld"
created: "2020-01-01T00:00:00Z"
modified: "2020-01-01T00:00:00Z"
---

# State what a mitigation newly makes possible

## Principle

every change to a running system creates interactions that did not exist before it. A fix is also a new failure surface, and it arrives with less operational experience behind it than the thing it replaced.

## Use when

recommending a retry, timeout, failover, circuit breaker, cache, autoscaling rule, or any other mitigation.

## Required behavior

name the failure mode the mitigation introduces and how it would be detected. Say what the system does when the mitigation itself misfires — retries amplifying load, a failover flapping, a stale cache served as fresh.

## Avoid

presenting a mitigation as a net reduction in risk without accounting for the risk it adds.

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
    "flow:locator": "thesis 14"
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
    "@id": "flow:entry/sre/state-what-a-mitigation-newly-makes-possible",
    "@type": "LearningResource",
    "name": "State what a mitigation newly makes possible",
    "audience": {
      "@type": "Audience",
      "audienceType": "sre"
    },
    "flow:layer": "baseline",
    "abstract": "every change to a running system creates interactions that did not exist before it. A fix is also a new failure surface, and it arrives with less operational experience behind it than the thing it replaced.",
    "flow:trigger": "recommending a retry, timeout, failover, circuit breaker, cache, autoscaling rule, or any other mitigation.",
    "flow:requiredBehavior": "name the failure mode the mitigation introduces and how it would be detected. Say what the system does when the mitigation itself misfires — retries amplifying load, a failover flapping, a stale cache served as fresh.",
    "flow:failureMode": "presenting a mitigation as a net reduction in risk without accounting for the risk it adds.",
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
        "flow:locator": "thesis 14"
      }
    ],
    "teaches": [
      {
        "@type": "DefinedTerm",
        "@id": "flow:competency/make-applicability-conditions-explicit-alongside-a-recommended-pattern",
        "name": "Make applicability conditions explicit alongside a recommended pattern"
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
