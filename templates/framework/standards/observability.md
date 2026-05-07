# Observability Standard

This standard defines the minimum operational visibility a project should have from day one.

## Core principle

Monitoring tells you something is wrong. Observability should help you ask why without already knowing the exact question.

Metrics, logs, and traces are most useful when they are correlated.

## Logging

- logs should be structured and consistent
- log levels should be meaningful
- logs should include enough context to explain what operation failed and where
- logs should include correlation context that ties them to metrics or traces when available

## Metrics and service signals

Useful patterns:

- RED for services: rate, errors, duration
- USE for resources: utilization, saturation, errors

Projects should choose a small set of meaningful signals around:

- usage
- failure rate
- latency or duration
- sync or background-job health
- resource consumption when the platform exposes it

## Tracing

For distributed or async systems, trace context should propagate across service and message boundaries where the stack supports it.

## Alerting and SLOs

Projects should define reliability targets before incidents force ad hoc decision-making.

Useful concepts:

- SLI
- SLO
- error budget
- burn-rate alerting

Alerting should favor actionable service degradation over noisy symptom counts.

## Safety rules

- errors should carry useful context
- secrets and sensitive data should not be logged
- work that changes runtime behavior should define how it will be verified

## Runtime verification

Local tests are not the whole operational story.

When runtime behavior changes, define:

- how deployment is verified
- what logs or metrics are inspected
- what degraded states should still be surfaced

## Relevant standards and tools

Principles:

- OpenTelemetry-style instrumentation
- RED / USE
- SLO and error-budget thinking
- DORA metrics for delivery health

Common tools:

- OpenTelemetry
- Prometheus / OpenMetrics
- Jaeger / Tempo
- Fluentd / Vector
- OpenSLO
