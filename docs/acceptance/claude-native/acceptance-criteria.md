# Acceptance Criteria — `greeting` rejects an empty name

- Work ID: claude-acceptance
- Stage: define (business-analyst)
- Date: 2026-10-11
- Companion: `requirements.md` in this directory
- Status: draft for Flow approval — writing this file does not approve the work

## Basis and standing assumptions

These criteria encode assumptions **A1–A3** from `requirements.md`. They are judgement calls, not facts from the fixture:

- **A1** — rejection is a raised exception, `ValueError` for empty values.
- **A2** — "empty" covers `""` and whitespace-only strings.
- **A3** — `None` is rejected as `TypeError`.

If a reviewer overturns any of these, the affected criteria (noted inline) change with it. Resolve **OQ1–OQ3** before the build stage.

Current behaviour, for contrast: `greeting` is `return f"Hello, {name}!"` with no validation (`fixture.py:1-2`), so `greeting("")` produces `"Hello, !"` today. **AC-1, AC-2, AC-3, and AC-5 all fail against the current file** — that is deliberate, and is how the suite proves it is testing the new behaviour rather than passing vacuously.

## Criteria

### AC-1 — Empty string is rejected

**Given** the `greeting` function
**When** it is called as `greeting("")`
**Then** it raises `ValueError`
**And** no string is returned.

- Verify: `pytest.raises(ValueError): greeting("")`
- Status against current code: **fails** (returns `"Hello, !"`)
- Covers: G1, G2, US1

### AC-2 — The rejection is diagnosable

**Given** a call rejected under AC-1
**When** the caller inspects the exception message
**Then** the message is non-empty and names the offending parameter (`name`).

- Verify: assert `str(exc.value)` is truthy and contains `"name"` (case-insensitive). Exact wording is intentionally not pinned — see OQ4.
- Status against current code: **fails** (no exception raised)
- Covers: G2

### AC-3 — Whitespace-only input is rejected *(depends on A2 / OQ1)*

**Given** the `greeting` function
**When** it is called with a string containing only whitespace — at minimum `" "`, `"   "`, `"\t"`, and `"\n"`
**Then** each call raises `ValueError`, identically to AC-1.

- Verify: parametrised `pytest.raises(ValueError)` over those four inputs.
- Status against current code: **fails** (`greeting("   ")` returns `"Hello,    !"`)
- Covers: G1, G2
- **Delete this criterion if OQ1 is resolved as "whitespace-only is acceptable input".**

### AC-4 — Valid names behave exactly as before

**Given** the `greeting` function
**When** it is called with any non-empty name
**Then** it returns `f"Hello, {name}!"` with no change to the string.

Concrete cases, each asserting exact equality:

| Input | Expected output | Why this case |
|---|---|---|
| `"Andy"` | `"Hello, Andy!"` | ordinary name |
| `"a"` | `"Hello, a!"` | shortest valid input — boundary just past empty |
| `" Andy "` | `"Hello,  Andy !"` (two spaces after the comma, one before the `!`) | surrounding whitespace must **not** be stripped; validation is a check, not a transform |
| `"Ana María"` | `"Hello, Ana María!"` | non-ASCII passes through unchanged |
| `"名前"` | `"Hello, 名前!"` | non-Latin script passes through unchanged |
| `"O'Brien"` | `"Hello, O'Brien!"` | punctuation is not filtered (NG1) |

- Status against current code: **passes** — intentionally. This is the regression guard; it must pass both before and after the change.
- Covers: G3, US2, NG2
- Note: the `" Andy "` case is the one most likely to be broken by a careless implementation that calls `.strip()` on the input instead of only on the emptiness check. Required behaviour: strip **for the check**, return the **original** string in the output.

### AC-5 — `None` is rejected *(depends on A3 / OQ2)*

**Given** the `greeting` function
**When** it is called as `greeting(None)`
**Then** it raises `TypeError`
**And** does not return `"Hello, None!"`.

- Verify: `pytest.raises(TypeError): greeting(None)`
- Status against current code: **fails** (returns `"Hello, None!"`)
- Covers: G1, G2
- **If OQ2 is resolved as "one exception type for all bad input", change the expected type to `ValueError` and merge this into AC-1.**

### AC-6 — Non-string types keep their current behaviour *(pins OQ3)*

**Given** the `greeting` function
**When** it is called with a non-string, non-`None` value such as `0`, `42`, or `[]`
**Then** behaviour is unchanged from today — the value is stringified into the greeting, e.g. `greeting(0) == "Hello, 0!"`.

- Status against current code: **passes** — intentionally.
- Rationale: this change is scoped to empty names (NG1). The criterion exists so that "we did not validate types" is a recorded decision rather than an oversight, and so a future tightening has to change a test on purpose.
- **Delete or invert this criterion if OQ3 is resolved as "validate types too".**

### AC-7 — The change is covered by automated tests

**Given** the implementation slice is complete
**When** the test suite is run
**Then** AC-1 through AC-6 exist as executable tests
**And** the full suite passes
**And** AC-1, AC-2, AC-3, and AC-5 are confirmed to fail when run against the pre-change `fixture.py`.

- Verify: run the suite against the current file and record the four failures, then against the changed file and record a clean pass. The first half is what proves the tests are not vacuous.
- Status: **not yet satisfiable** — no test file exists in this project (`find` returned only `./fixture.py`). The implementation slice must create one.
- Covers: G4, US3

### AC-8 — The diff stays within scope

**Given** the implementation slice is complete
**When** the diff is reviewed
**Then** only `fixture.py` and the new test file are modified
**And** `greeting`'s signature is unchanged — one positional parameter `name`, no default
**And** no new third-party dependency is introduced
**And** the success-path return expression still produces `f"Hello, {name}!"`.

- Verify: `git diff --stat` on the implementation branch, plus a read of the changed function.
- Covers: NG2, NG3, and the signature constraint in `requirements.md` § Scope

## Coverage map

| Goal / story | Criteria |
|---|---|
| G1 — reject empty name | AC-1, AC-3, AC-5 |
| G2 — rejection is unambiguous | AC-1, AC-2, AC-3, AC-5 |
| G3 — valid names unchanged | AC-4, AC-6, AC-8 |
| G4 — automated coverage | AC-7 |
| US1 — fails loudly at the call site | AC-1, AC-2 |
| US2 — no work for existing callers | AC-4, AC-8 |
| US3 — pinned against regression | AC-7 |

## Not verified by these criteria

Stated so the gaps are visible rather than assumed covered:

- **Behaviour under a different Python version.** AS3 assumes 3.6+; nothing in the workspace pins a version (no `pyproject.toml`, `setup.py`, or equivalent), and these criteria are not run across versions.
- **Caller-side handling of the new exception.** There are no callers (E4), so nothing downstream is exercised.
- **Performance.** Out of scope for a two-line function; no criterion addresses it.
- **The exception message wording.** AC-2 checks shape, not copy — deliberately, per OQ4.

## Definition of done

All of AC-1 through AC-8 pass, **and** OQ1, OQ2, and OQ3 have a recorded decision from the reviewer — because AC-3, AC-5, and AC-6 each change or disappear depending on how those land. Flow's approval of this stage, not this document, is what releases the work to the build stage.
