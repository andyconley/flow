## Data Review Summary

### Schema Impact

- V7 stores Shaper, Charter, handoff, and Delivery Lead links in the immutable
  envelope. `attempts.owner_generation` now initializes from that claim.
- Run authority uses immutable, digest-keyed artifact directories and a mutable
  `run.json.delivery` pointer. Ledger changes remain additive.

### Integrity Review

#### Resolved — canonical start-plan artifacts use their digest-keyed directory

Preparation now requires `delivery_artifact_dir`, validates it as a run-local
path, and reads Shaper Contract, Delivery Charter, and handoff from that exact
location ([cli/delivery_gateway.py](../../../../cli/delivery_gateway.py):66-87).
The chartered-delivery fixture now supplies the same authority shape
([tests/test_chartered_delivery_gateway.py](../../../../tests/test_chartered_delivery_gateway.py):77-87).

#### Resolved — stale owner cannot mutate after run-level supersede

V7 attempt creation takes its generation and actor from the claim
([cli/execution_ledger.py](../../../../cli/execution_ledger.py):224-233). The
per-run authority guard compares current claim digest, Charter digest, and
generation to the envelope ([cli/delivery_control.py](../../../../cli/delivery_control.py):39-55), and
now surrounds v7 decision, send, and receipt-seal boundaries
([cli/delivery_gateway.py](../../../../cli/delivery_gateway.py):767-807,
818-855, 962-973). The supersede-after-preparation test confirms that no worker
send or receipt seal occurs ([tests/test_chartered_delivery_gateway.py](../../../../tests/test_chartered_delivery_gateway.py):123-144).

#### Resolved — delivery-lead event idempotency preserves generations

Event identity now includes `owner_generation`
([cli/delivery_control.py](../../../../cli/delivery_control.py):82-108), so a
later successor no longer suppresses an earlier claim's audit event.

#### Resolved — interrupted staging no longer conflicts with corrected sources

Digest-keyed directories leave failed stages inert and let a corrected retry
use a new authority location ([cli/delivery_control.py](../../../../cli/delivery_control.py):164-170),
covered by the changed-source test
([tests/test_delivery_control.py](../../../../tests/test_delivery_control.py):123-130).

### Query and Index Review

- Attempt lookup, action lookup, and event ordering use primary keys or
  attempt-scoped predicates. The new `actions_attempt_kind_sequence` index
  supports the ordered delegation check in `decide`.
- Migration attempts the unique index after adding legacy defaults, then falls
  back to a non-unique lookup index when historical positions collide
  ([cli/execution_ledger.py](../../../../cli/execution_ledger.py):155-171).
  That preserves readable multi-action legacy ledgers; transactional slot
  checks remain the authority for new writes.

### Migration Plan

- **Compatibility verdict: acceptable for v7 handback.** The run claim,
  execution envelope, ledger generation, and provider boundary are now
  generation-fenced. The old ledger path remains readable, including duplicate
  historical action positions.
- Execute schema evolution in one explicit transaction and record a schema
  migration/version marker. Current initialization mixes `executescript`,
  `ALTER TABLE`, and index creation without a durable migration marker
  ([cli/execution_ledger.py](../../../../cli/execution_ledger.py):52-168), so a
  failed index creation can leave a partially evolved database.
- Rollback is forward-only: retain added columns/tables, select legacy
  records through the existing read-only projection, and disable v7 dispatch
  for an attempt whose stored claim cannot be reconciled.

### Risks

- Critical: none found.
- High: none found.
- Medium: SQLite initialization has no durable migration version/history
  marker; retain this as operational hardening follow-up.
