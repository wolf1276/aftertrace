# HydraDB context catalog (Phase 3)

## Run

From `aftertrace/`, after starting the Phase 1 runtime:

```sh
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/ingest_context.py
.venv/bin/python scripts/ingest_context.py --field delivery_events.event_id
AFTERTRACE_LIVE_TEST=1 .venv/bin/python -m unittest discover -s tests -v
```

The command builds a healthy synthetic fixture, introspects actual DuckDB schemas, writes metadata into HydraDB, then retrieves the KPI's bounded field neighborhood, contracts, and relevant diagnostic-tool descriptions. It does not ingest expected causes, scenario labels, or repair answers.

## Schema and lineage

- Dataset schemas and field types/nullability come from `DESCRIBE` against actual fixture relations.
- Dataset lineage and matching-name column mappings are declared for our owned SQL pipeline: `delivery_events -> normalized_events -> shipment_facts -> delivery_fee_kpi`.
- Aggregate fee cardinality also depends on canonical event identity, represented as an event-identity-to-KPI edge. These are declared dependencies, not an automatic SQL lineage parser.
- `carrier_heartbeats` is a disconnected diagnostic feed, not invented upstream lineage.
- Field contracts describe intended identity, completeness, and currency semantics, independent of any broken scenario.
- `Tool` nodes register read-only diagnostic capabilities and compatible fields. Tool execution and agent planning are Phase 4, not provided by this metadata layer.

Relationships: `FEEDS`, `HAS_FIELD`, `DERIVES`, `GOVERNED_BY`, and `INSPECTS`.

## Query interface

```python
from app.config import connect
from app.graph import ContextGraph

graph = ContextGraph(connect())
graph.seed()  # repeatable ingestion
all_context = graph.context()
assets = graph.search('shipment')
upstream = graph.upstream('delivery_fee_kpi.fee_cents', max_hops=3)
focused = graph.field_context('delivery_fee_kpi.fee_cents')
```

Returned records identify `hydradb` as their source, include application scope, and expose retrieval counts. Traversal supports 1–4 explicit hops, excludes the starting field from cycles, and records shortest observed depth. The default is a 32-field traversal budget, with a maximum of 64. Full catalogs default to a 128-node budget (maximum 256). Exceeding a budget fails explicitly rather than silently truncating evidence.

Search is case-insensitive substring matching over this small, bounded catalog, performed client-side after loading app-owned assets. This is not a full-text engine or large-catalog search implementation.

## Identity and safe writes

- IDs are deterministic positive numeric SHA-256 prefixes over application scope, fixture version, node kind, and stable key.
- In-memory duplicate IDs and existing database key mismatches are rejected before metadata writes. A hash collision does not overwrite another key.
- Each node stores its full stable key and owner scope. Independent scopes have different IDs and reads filter owner.
- Labels/properties are upserted before edges. The tested HydraDB `UNWIND ... CREATE` edge-batch shape is repeatable without multiplying relationships.
- Parameters carry values; query labels/relationship types and fixture relation identifiers come only from module constants.
- A catalog manifest stores its schema/metadata fingerprint. Schema changes under the same version/scope fail: bump the fixture version or use a new scope intentionally.
- The manifest stays `pending` until ingestion finishes. Incomplete catalogs cannot be used for investigations. Re-running identical ingestion resumes safely, then reconciles actual node/edge counts.

The manifest is a single-operator publication guard, not a transaction or distributed ingestion lock. Concurrent catalog writers are out of scope for this local release. Do not expose ingestion as an unauthenticated public operation.

## Isolation and tests

Live graph tests create random `graph-test-*` scopes, test real HydraDB, and delete only IDs derived from that scope. They cover repeat ingestion, actual multi-hop lineage, contract/tool retrieval, missing assets, empty neighborhoods, cycles, budgets, schema drift, collision rejection, and recovery from an injected edge-write interruption.

No silent in-memory graph fallback exists. HydraDB unavailability raises an explicit transport error. Incident evidence, repair memory, and learning evaluation remain later phases.
