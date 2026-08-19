# Evidence Standard

This standard defines what makes a claim of proof trustworthy: what the prover
was told already existed, where the proof was collected, and whether the proof
could have failed.

## What a brief must carry

Any brief that asks someone to review, audit, or look for what is missing must
state what already exists. Without it, "X is missing" is an unsupported finding
— the reviewer had no way to distinguish absent from unfound.

An evidence inventory names, for the area under review:

- what already exists, with file paths and line references
- what is partially covered, and by what
- what was checked and genuinely found absent

Defaults:

- `DO` write the inventory before dispatching the brief, not after
- `DO` cite a path or a line for each claim of coverage
- `AVOID` "nothing exists for X" without saying where you looked

## The inventory is only as good as the search behind it

An inventory is itself evidence and carries the same burden as any other.
A case-sensitive search, a wrong directory, or an unchecked assumption produces
an inventory that is confidently wrong, and every reviewer who trusts it
inherits the error.

Defaults:

- `DO` state how you searched, so a reader can judge the search
- `DO` correct the inventory in place when a reviewer disproves an entry, and
  say what changed
- `DO NOT` treat an inventory as settled because it was written down

## Relevant principle

An inventory converts "I did not find it" into "it is not there" — but only
when the search is stated. Unstated, it converts one reviewer's blind spot into
everyone's.
