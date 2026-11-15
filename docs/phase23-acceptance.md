# Phases 2 and 3 acceptance

## Scope and ownership

Head agent led graph implementation, integration, and acceptance. OpenCode exclusively owned `app/fixture.py`, `tests/test_fixture.py`, and `docs/FIXTURE.md` during its run. Its JSON event log was monitored at `/tmp/aftertrace-agents/phase23-opencode.jsonl`. OpenCode completed before the head added two verifier regression checks and updated its documentation; there were no concurrent edits to shared files.

No landing page, outreach, or public publication was performed.

## Phase 2: executable synthetic fixture

- Fixture `fulfillment-v2`, versioned generation/contracts/transforms, invariant suite `invariants-v2.1`.
- Actual DuckDB pipeline: raw delivery events -> normalized events -> shipment facts -> daily fee KPI.
- Four cases: healthy, duplicate, duplicate with different source/event identifiers, and missing late shipments.
- Non-critical stale carrier-heartbeat distractor does not contribute to fee lineage.
- Deterministic measurements include daily fees, duplicates, nulls, source partitions, completeness, and reconciliation.
- Eleven invariants check uniqueness, completeness, fees, coverage, accepted-row accounting, partition conservation, required values, and exact preservation of canonical event contents.
- Fixture is deliberately shipment/delivery-focused; a separate orders subsystem adds no value to this demonstration and was not built.

Actual seed-7 results:

| Scenario | Transform | Rows | Fees (cents) | Checks passed |
| --- | --- | ---: | ---: | ---: |
| Healthy | Original | 100 | 54550 | 11/11 |
| Healthy | Deduplicated | 100 | 54550 | 11/11 |
| Duplicate | Original | 154 | 83914 | 6/11 |
| Duplicate | Deduplicated | 100 | 54550 | 11/11 |
| Held-out identifiers | Original | 154 | 83914 | 6/11 |
| Held-out identifiers | Deduplicated | 100 | 54550 | 11/11 |
| Missing shipments | Original | 79 | 42973 | 9/11 |
| Missing shipments | Deduplicated | 79 | 42973 | 9/11 |

Dropping a source partition, relabeling event IDs while preserving totals, and nulling required values are rejected in tests. This verifies fixture mechanics and candidate invariants, not an autonomous diagnosis or learning claim.

## Phase 3: actual HydraDB context graph

The actual fixture's schemas were introspected and ingested into the live self-hosted runtime:

- **46 nodes and 63 edges**, identical on a second ingestion.
- Directed dataset and field dependencies, contracts, and diagnostic tool registry.
- KPI context retrieved six upstream fee/identity fields over three hops.
- Relevant tools retrieved: `fee_reconciliation` and `duplicate_profile`.
- Contracts and tool descriptions come from actual HydraDB reads.
- Scope-aware deterministic IDs with full-key collision checks.
- Labels before idempotent edge batches; pending manifest rejects partially ingested catalogs.
- Real integration tests cover recovery after an injected edge-write failure, schema drift, missing scopes/assets, disconnected neighborhoods, cycles, and traversal budgets.

Lineage is explicitly declared for the owned fixture, not automatically parsed from arbitrary SQL. Tool nodes describe capabilities; Phase 4 must implement safe diagnostic dispatch and investigation.

## Reproduce

From `aftertrace/` with the Phase 1 runtime running:

```sh
.venv/bin/pip install -r requirements.txt
AFTERTRACE_LIVE_TEST=1 .venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/check_fixture.py --scenario duplicate --seed 7
.venv/bin/python scripts/check_fixture.py --scenario duplicate --seed 7 --candidate deduplicated
.venv/bin/python scripts/ingest_context.py
```

**Result: 41 tests passed, none skipped with live checks enabled.** This includes 17 fixture tests, 7 catalog/graph tests, and 17 existing transport tests. Five tests use the real HydraDB engine. Source compilation checks passed.

Raw local receipts: `data/receipts/phase2-fixtures.json`, `phase2-cli.json`, `phase3-ingest.json`, and `phase3-reingest.json`. These ignored runtime artifacts are not fabricated benchmark results.

## Remaining limits

- Synthetic, small fixture and declared lineage only; no production connector.
- Identifier/partition holdouts are variants of one incident family, not proof of generalization across incident types.
- Local single-operator ingestion; no distributed transaction/ingestion lock.
- Full-catalog substring search is bounded client-side, not scalable full-text search.
- Scenario truth and candidate SQL remain in trusted fixture/verifier code; future investigation tools must not expose generator/test answers or unrestricted Python/SQL.
- Evidence-gated investigation, approvals, sandboxed repair orchestration, repair memory, UI, and learning evaluation are not implemented by these phases.
