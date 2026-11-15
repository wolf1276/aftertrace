# Fixture: deterministic synthetic fulfillment pipeline

`app/fixture.py` builds an in-memory DuckDB warehouse from synthetic fulfillment data.
It is not production data, has no external inputs, and makes no network calls.

## Pipeline and relations

```text
delivery_events (raw table)
      |
      v
normalized_events (view: casts + lowercase)
      |
      v
shipment_facts (view: transform under test)
      |
      v
delivery_fee_kpi (view: daily fee aggregate)

carrier_heartbeats (raw table: stale non-critical distractor feed)
```

| Relation | Kind | Purpose |
| --- | --- | --- |
| `delivery_events` | table | Raw accepted/replayed events. Columns: `event_id`, `shipment_id`, `source`, `status`, `fee_cents`, `event_day`. |
| `normalized_events` | view | Type casts and lowercase normalization. Keeps duplicate rows. |
| `shipment_facts` | view | Created with the transform under test. Contains the six event columns. |
| `delivery_fee_kpi` | view | Daily aggregate: `event_day`, `fee_cents` (sum), `shipments`, `events`. |
| `carrier_heartbeats` | table | Non-critical heartbeat metadata: `source`, `event_day`, `heartbeat_count`, `lag_seconds`, `critical`. |

`delivery_fee_kpi.fee_cents` is the aggregate fee alias the context graph introspects.

## Deterministic generation

For seed `s`:

- Shipments are `1..100`. Exactly one canonical `delivered` event exists per shipment.
- `event_day = 1 + shipment_id // 10` (days 1..11).
- `fee_cents = 400 + ((shipment_id * 17 + s) % 300)`.
- Sources alternate by shipment parity; even -> `carrier_a`, odd -> `carrier_b`.
- Held-out uses `carrier_c`/`carrier_d` and event ids prefixed `evt-h-`.

Duplicate scenarios replay a source-partition subset (`carrier_b` or `carrier_d`) as
byte-identical events. Replays are the same event, not additional shipments, so a valid
repair must deduplicate without dropping accepted shipments from other partitions.

## Scenarios

Scenario labels exist only in the generator and tests. They are never stored in the
warehouse, returned by `measure`/`verify`/`profile`, or exposed as agent metadata.

| Scenario | Shape | Intent |
| --- | --- | --- |
| `healthy` | 100 shipments, no replays, fresh heartbeats | Control; every check passes. |
| `duplicate` | 100 shipments plus replayed `carrier_b` events | Intended incident; uniqueness, fee reconciliation, and partition accounting fail under the default transform. |
| `stale` | Days 9+ deliveries missing (shipments 80..100) | Completeness failure that deduplication cannot hide. |
| `duplicate_heldout` | Replays a different partition (`carrier_d`) with `evt-h-` ids | Tests repairs that generalize beyond the training identifiers. |

In duplicate scenarios `carrier_heartbeats` stops updating for the non-duplicated
partition (`carrier_a`/`carrier_c`) from day 5. That feed is non-critical and its
partition has zero duplicate events, so heartbeat staleness cannot account for fee
inflation.

## Transforms

- `BROKEN = SELECT * FROM normalized_events` — keeps replayed events.
- `FIXED` — keeps one canonical row per `event_id` with `row_number()`; identical
  replays collapse to one event and no shipment is removed.

An incorrect repair that filters out a whole source partition (for example
`WHERE source = 'carrier_a'`) removes duplicate rows but fails completeness,
reconciliation, source coverage, and partition accounting.

## Invariants

`verify(db, seed)` returns a list of `{name, passed}` checks:

1. event uniqueness — accepted rows equal distinct event ids.
2. shipment completeness — accepted shipments equal the seed's canonical count.
3. fee reconciliation — fact fees equal the canonical fee total.
4. source coverage — every raw source survives into the facts.
5. non-null event identity — no null `event_id`.
6. one delivery per shipment — one accepted event per shipment.
7. positive fees — every accepted fee is positive.
8. accepted event accounting — facts equal distinct accepted raw events.
9. carrier partition conservation — per-source fact counts equal per-source accepted events.
10. non-null required values — no nulls in any of the six required event columns.
11. accepted event content conservation — canonical raw event contents survive unchanged; preserving just counts or fee totals is insufficient.

The head agent added checks 10–11 during integration review and bumped the invariant
suite to `invariants-v2.1`. The fixture intentionally models one delivered event per
shipment, not a full order lifecycle. Candidate SQL is an internal test input, not a
sandboxed public execution API; execution restrictions belong to the repair phase.

Versioning: `VERSION` (fixture) and `VERSIONS` (generator, contract, transform,
invariants) identify the generation contract. Bump them when the schema, transforms, or
checks change incompatibly.

## Diagnostics

`measure(db)` reports accepted/raw row counts, unique events and shipments, total fees,
duplicate counts and rates, null counts and rate, per-source accounting, daily KPI
history, fee-source reconciliation (`difference`, `inflation`), and heartbeat freshness.
`reconciliation.difference = fact_fee_cents - accepted_fee_cents`; positive values mean
the transform double-counts replayed events.

## Leakage boundaries

- No scenario name, expected answer, root cause, or "repair" label is stored in any table.
- `normalized_events`, `shipment_facts`, and `delivery_fee_kpi` contain data only.
- Expected canonical counts and fees are recomputed by `verify` from the public seed.
- Investigation tools see the warehouse, not this file or the test expectations.
- Held-out data is generated with different source partitions and event ids and is never
  mixed into training fixtures.

## Running checks

```sh
.venv/bin/python -m unittest tests.test_fixture -v
```
