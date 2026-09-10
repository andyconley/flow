# Product-manager evaluation design

## Primary case

Two customer requests compete for the next release: a dashboard export used by
six weekly active operators with repeated manual workarounds, and a new
integration requested by one executive sponsor. Evidence includes support
frequency, estimated effort, and a fixed two-week release window. Ask for a
priority decision and smallest useful slice.

Pass: state the outcome, choose or defer explicitly, name the tradeoff, and
state evidence that would change the decision. Failure: turn the answer into a
business-analysis interview, architecture design, or implementation task list.

## Counter-case

A statutory invoice-field change has a fixed legal date, settled scope, and an
attached rule. Ask for release prioritization.

Pass: sequence the required work and identify delivery risk without inventing
an outcome experiment or reopening settled discovery.

## Added discriminating primary case (approved 2026-09-09)

Two dashboard-export proposals fit the same two-week window. One removes the
operators' existing manual workaround but has no scheduled-delivery feature.
The other adds scheduled delivery, has a larger sponsor list, but does not
remove the documented workaround. Support frequency is identical. Ask for the
release decision and smallest useful slice.

Pass: choose based on the outcome to change, distinguish feature popularity
from outcome evidence, state the smallest slice, and name the observation that
would reverse the decision.
