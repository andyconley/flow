# Workflow Standard

This standard defines how work types map onto the available `flow` lanes.

## Command mapping

- small change -> `/flow-scout`
- vague feature or architectural capability -> `/flow-define`
- approved requirements needing technical options -> `/flow-solution`
- shaped implementation -> `/flow-implement`
- planning-heavy change -> `/flow-plan`

## Default guidance

- use `/flow-boot` at the start of a session or before resuming interrupted work
- use `/flow-define` when feature or capability requirements are not yet approved
- use `/flow-plan` when approved requirements or bug-shaped work need implementation shaping
- use `/flow-scout` for small work that should stay narrow
- use `/flow-implement` for durable, reviewable execution

## Escalation rule

If small work grows into cross-file, cross-session, or contract-shaping work, escalate out of scout mode instead of letting an ad hoc fix quietly become a larger workflow.

## Relevant principle

Workflow selection is a risk-management tool. The lane should match the uncertainty, blast radius, and durability needs of the work.
