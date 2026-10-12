# Acceptance Criteria

## Scenario 1: Valid Name
- **Given** a non-empty string `name` (e.g., `"Alice"`)
- **When** the `greeting(name)` function is called
- **Then** it should return the string `"Hello, Alice!"`

## Scenario 2: Empty Name
- **Given** an empty string `name` (`""`)
- **<b>When</b>** the `greeting(name)` function is called
- **Then** it should raise a `ValueError` (or another appropriate exception) indicating that the name cannot be empty.

## Scenario 3: Whitespace Name (Optional/Definitional)
- **Given** a string `name` consisting only of whitespace (e.g., `" "`)
- **When** the `greeting(name)` function is called
- **Then** it should [be defined as either accepting or rejecting, preferably rejecting if following the 'empty name' spirit]. 
  *Note: Requirement specifies 'reject an empty name', which strictly implies `""`. However, for robustness, whitespace rejection is a recommended consideration.*
