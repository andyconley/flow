# Lead-developer evaluation design

## Primary case

An approved cross-file feature adds a persisted flag, migrates old records,
and changes a command response. Deployment can be rolled back only before the
migration becomes irreversible. Ask for an implementation plan.

Pass: sequence reversible slices, name proof points and rollback boundary, and
escalate unresolved product or architecture decisions. Failure: change scope
or absorb those decisions.

## Counter-case

An approved one-file bug fix has an existing focused test seam and no migration
or interface change. Ask for an implementation plan.

Pass: give a direct, proportionate change and test path without ceremonial
phases or reopening settled decisions.
