# Planning brief: implementation structure

## Role

Act as Flow's architect. Recommend the smallest structurally sound change and
its file-level sequence.

## Inputs

- `requirements.md`
- `acceptance-criteria.md`
- `research/architecture-challenge.md`
- `review/architecture.md`
- the current working tree and commit `2712f5f`

## Questions to answer

1. Which active source/config/vocabulary/test/document surfaces are retained,
   restored, removed, generated, or newly added?
2. How should the implementer restore PM/QR exactly while retaining the three
   passing roles and keeping both historical evidence roots byte-identical?
3. Where should the new current-release summary and final receipt live?
4. What branch, review, merge, semantic-release, and recovery sequence avoids
   claiming success before remote and installed readback?

Write the result to `research/plan-architecture.md`. Do not edit production
files or protected evidence.
