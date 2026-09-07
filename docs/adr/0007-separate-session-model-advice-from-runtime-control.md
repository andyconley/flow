# ADR 0007: Separate session model advice from runtime control

Status: Accepted
Date: 2026-09-07
Related work: session-model-recommendation

## Context

Five Flow entry commands need consistent advice across Claude and Codex.
Existing tiers configure delegated roles; they do not observe or control the
parent session. Usage records measure consumption and capacity, not task
correctness or inference speed. Generated routing hints also need the same
effective resolver used by generated agent files.

## Decision

Use one shared qualitative task rubric, a small read-only facts boundary, and
deterministic runtime profile resolution. Quality and confidence take
precedence, followed by supported speed considerations. Cost stays
informational. Define separate parent-session profiles with runtime-native
mappings and explicit provenance; do not extend ADR 0003's boolean permission
catalog.

Advice is transient unless captured in existing plan or solution artifacts. It
does not mutate model settings, add lifecycle gates, harvest data, or claim a
switch. Unknown scope, identity, history, or availability stays explicit.
Missing exact mapping preserves semantic advice without lowering the required
posture.

Ordinary entry advice stays within the active runtime. Cross-provider comparison
or migration requires a separate explicit request and evidence for both
providers. Public CLI parent input remains declared because caller input cannot
prove freshness or same-session binding. A future runtime adapter may label
identity observed only after it validates a supported source, freshness, and
binding.

Share effective delegated-agent resolution between generated agent settings and
routing hints while preserving tier, runtime override, then generic override
precedence. Keep parent profiles separate from delegated-agent overrides.

## Alternatives considered

Shared prose alone leaves evidence interpretation and resolution too variable.
A deterministic task table adds taxonomy maintenance and still cannot infer
quality from telemetry. Learned or numeric model ranking requires a separate
labeled outcome contract and remains outside this decision.

## Consequences

The design adds a small configuration and CLI contract plus cross-runtime
scenario evaluation. Exact mappings remain reversible configuration. There is
no new database or provider call at entry.

The first concrete profile mappings were selected before implementation and
must pass authenticated use in both clients. Account entitlement is not inferred
from catalogs or syntax. The profile resolver stays swappable as models change,
while parent advice remains separate from delegated-agent configuration.

This release does not prove which commercial model gives the highest quality.
Future changes can refine mappings or the rubric using explicit evidence without
building an automatic model-routing platform.
