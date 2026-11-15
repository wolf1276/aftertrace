# Aftertrace

A new data-incident context workbench built for HydraDB.

## Product contract

Investigate an affected dataset through bounded lineage, collect reproducible evidence, require operator approval before repair, verify the candidate against invariants, and remember only verified repairs. Historical repairs are investigation hints, never proof about a new incident.

HydraDB holds dataset contracts, field lineage, tool capabilities, evidence provenance, and verified repair relationships. Warehouse execution remains separate from graph storage.

## Implementation status

This directory is a new implementation, not a renamed copy of the reference application. Phases 1–3 are complete: self-hosted durable HydraDB, hardened transport, deterministic DuckDB incident fixtures, 11 invariants, and bounded graph/contract/tool retrieval. All 41 unit/integration tests pass with live HydraDB checks enabled. The actual fixture ingests as 46 nodes and 63 edges, identically on repeat ingestion. Investigation, approved repair orchestration, memory, UI, and the learning benchmark remain unfinished.

## Start the local runtime

```sh
python3 scripts/setup_runtime.py
python3 -m venv .venv
docker compose up -d
# Wait for HTTP 200 from http://127.0.0.1:19091/readyz
.venv/bin/python scripts/runtime_smoke.py
AFTERTRACE_LIVE_TEST=1 .venv/bin/python -m unittest discover -s tests -v
```

Phase 1 requires only Python's standard library and Docker Compose. See [the runtime runbook](docs/RUNTIME.md) and [acceptance receipt](docs/phase1-acceptance.md). Plaintext networking is loopback-only; this is not a production deployment.

Run the client tests:

```sh
python3 -m unittest discover -s tests -v
```

## Run the fixture and context graph

```sh
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/check_fixture.py --scenario duplicate --seed 7
.venv/bin/python scripts/check_fixture.py --scenario duplicate --seed 7 --candidate deduplicated
.venv/bin/python scripts/ingest_context.py
```

See [fixture details](docs/FIXTURE.md), [context graph](docs/CONTEXT.md), and [Phase 2–3 acceptance](docs/phase23-acceptance.md). Diagnostics and checks execute against real synthetic data; these are not autonomous investigation or learning results.

## Intended first vertical slice

- A synthetic fulfillment pipeline with duplicate shipment events, distinct from the reference fixture.
- Graph-guided investigation with attributable quantitative evidence.
- Operator-approved candidate repair in an isolated fixture, with row conservation and uniqueness checks.
- Verified-repair memory linked to the affected fields and tool used.
- A held-out comparison of investigations with and without memory; no improvement claims until measured.

## Connection configuration

The client accepts an explicit query endpoint, bearer token, graph, and cell. Credentials stay server-side. Local plaintext HTTP is permitted only for loopback; remote connections require HTTPS. HydraDB is not emulated when unavailable.
