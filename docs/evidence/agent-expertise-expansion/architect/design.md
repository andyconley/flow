# Architect evaluation design

## Primary case

A service boundary change has two viable compatibility options: preserve an
old API translation layer temporarily or require all callers to migrate in the
same release. Ask for the architecture decision.

Pass: state the decision, context, alternatives, tradeoffs, consequences, and
reversal conditions. Failure: make a product priority choice or write a
file-level implementation plan.

## Counter-case

A local helper refactor has no public interface, persistence, or cross-module
effect. Ask for architecture guidance.

Pass: identify it as an implementation-level choice and avoid creating an ADR
or widening the design.
