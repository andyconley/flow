# Definition brief: behavioral testability challenge

## Task

Determine whether any previously proposed product-manager or quality-reviewer
method is sufficiently absent from the unchanged role bodies to justify a new
behavioral envelope. Compare product reversibility classification and resolvable
success metrics; compare quality omission-first review and observed/read/asserted
verification labels. Design a bounded exploratory pre-screen and a later frozen
acceptance rule, or recommend deferral if the distinction cannot be tested
without overfitting. Write only to
`.flow/runs/role-method-differentiation-repair-3/research/testability-challenge.md`.

## Evidence inventory

### Already exists

- Unchanged control bodies at frozen commit `2712f5f1fb7f3ecabbc0bbcb77cdf9cd33431208`.
- Two generations of failed PM/QR comparisons and their raw outputs under
  `docs/evidence/agent-expertise-expansion/` and
  `docs/evidence/role-method-differentiation/repair-2/`.
- Formal review and test audit under
  `.flow/runs/role-method-differentiation/review.md` and `review/`.
- The engineer's four remaining candidate methods, including trigger, behavior,
  failure mode, and proposed source.

### Partially covered

- The candidates are textually absent in exact form, but the controls may infer
  some behaviors from ordinary role competence or fixture cues.
- Repair-2 has a product mutation check; quality mutation and repair-start
  preservation digests are absent.

### Checked and genuinely absent

- No exploratory candidate screen, versioned repair-3 fixture, rubric, or
  stopping rule exists.
- No evidence supports relaxing a strict treatment-over-control claim after the
  result is known.

### Search method

The coordinator compared the frozen control bodies with the candidate behaviors,
read both failed evidence sets and scorecards, and extracted the formal review's
false-pass and fixture findings.

## Required output

- Rank the four candidates by expected discriminability and role value.
- Specify exploratory fixtures that do not become acceptance evidence.
- Specify treatment/control/counter requirements and a stopping rule before live
  acceptance runs.
- Protect against vague metrics, invented inputs, formatting-only differences,
  generic competent inference, semantic negation, selective reruns, and rubric
  changes after scoring.
- Recommend proceed, narrow, or defer.
