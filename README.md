# Aftertrace

Aftertrace is an evidence-backed context workbench for data incidents. It keeps the catalog an investigation needs — datasets, fields, lineage, contracts, and diagnostic-tool capabilities — in HydraDB, while warehouse execution stays in a separate synthetic DuckDB fixture. The aim is to retrieve a small, relevant context subgraph instead of trusting yesterday's answer blindly.

**Status: local development prototype.** Phases 1–3 are implemented. Evidence-gated investigation, approval, isolated repair orchestration, verified-repair memory, API/UI, and learning evaluation are not part of this documented release. Fixture verification checks are implemented. This is not a production deployment and does not use an LLM.

## What works now

- Self-hosted, authenticated HydraDB with a durable named volume.
- A standard-library HTTP client with TLS enforcement for remote hosts, no redirect forwarding, bounded pagination, sanitized errors, and no automatic retries.
- A deterministic synthetic fulfillment warehouse with healthy, duplicate, held-out duplicate, and stale scenarios.
- Eleven executable invariants, including event identity/content conservation and carrier-partition accounting.
- Repeatable catalog ingestion from the actual fixture schema plus declared lineage: **46 catalog nodes and 63 edges**, identical on re-ingestion.
- Bounded reads for field neighborhoods, upstream lineage, contracts, and relevant diagnostic tools.
- The phase 1–3 baseline is **41 passing tests with live HydraDB checks enabled**; five are opt-in live tests.

## Architecture at a glance

```text
Operator shell
    |
    +-- Python CLI / modules
          |
          +-- DuckDB in-memory fixture (synthetic, disposable)
          |
          +-- HydraDB HTTP client --loopback bearer auth--> self-hosted HydraDB
                                                               catalog: datasets,
                                                               fields, contracts,
                                                               diagnostic tools
```

HydraDB is the context store. The warehouse is generated locally and is not the system of record. See [Architecture](docs/ARCHITECTURE.md) for boundaries, graph types, ingestion lifecycle, transport semantics, and limits.

## Quickstart (fresh clone)

Prerequisites: Python 3.12+, Docker Engine with Compose v2, and access to pull the pinned HydraDB image.

Clone the repository, then run from its root:

```sh
git clone https://github.com/wolf1276/aftertrace.git
cd aftertrace
python3 -m venv .venv
.venv/bin/python scripts/setup_runtime.py
.venv/bin/pip install -r requirements.txt
docker compose up -d
```

Wait for readiness with a bounded loop; do not rely on an unbounded sleep:

```sh
ready=0
for _ in $(seq 1 60); do
  if curl -fsS --max-time 2 -o /dev/null http://127.0.0.1:19091/readyz; then ready=1; break; fi
  sleep 1
done
[ "$ready" = 1 ] || { echo "HydraDB did not become ready"; exit 1; }
curl -fsS http://127.0.0.1:18443/healthz
```

`setup_runtime.py` creates a private `.env` with a random token and local endpoint defaults. It never displays the token and refuses to overwrite an existing `.env`. Ports are published on loopback only.

Run the authenticated transport smoke check:

```sh
.venv/bin/python scripts/runtime_smoke.py
```

## Try the synthetic incident

```sh
.venv/bin/python scripts/check_fixture.py --scenario duplicate --seed 7
.venv/bin/python scripts/check_fixture.py --scenario duplicate --seed 7 --candidate deduplicated
.venv/bin/python scripts/ingest_context.py
```

At seed 7, the duplicate scenario's default transform accepts 154 rows and reports 83,914 cents of fees against a canonical 100 rows and 54,550 cents; 6 of 11 invariants pass. The deduplicated candidate restores 100 rows, 54,550 cents, and 11/11 checks. The `stale` scenario still fails completeness after deduplication, and the held-out duplicate uses different source partitions and event IDs. These are actual fixture results, not a diagnosis or learning result.

`ingest_context.py` builds the healthy fixture, introspects its schemas, writes the catalog to the configured HydraDB scope, and prints the KPI field's bounded context. It does not ingest scenario labels, expected causes, or repair answers. Use `--scope` for an isolated catalog and `--field` for another starting field.

## Test

```sh
# Live tests skip unless explicitly enabled.
.venv/bin/python -m unittest discover -s tests -v

# Live run, including real HydraDB checks. Uses random scratch scopes and scratch IDs.
AFTERTRACE_LIVE_TEST=1 .venv/bin/python -m unittest discover -s tests -v
```

There is no lint, typecheck, or CI configuration in this repository.

## Limitations

- Synthetic data only: one small fulfillment incident family (100 shipments), not production connectors or real customer data.
- Not part of this documented release: investigation, evidence gates, approval, repair execution, verification orchestration, repair memory, API, UI, LLM planning, and learning evaluation.
- Lineage is explicitly declared for the owned fixture SQL; it is not parsed automatically. Search is bounded client-side substring matching, not full-text search.
- Single-operator local runtime: loopback plaintext HTTP, no multi-tenancy, no application-level authorization, no backups/HA certification, and no TLS termination included.
- The candidate transform argument is trusted internal Python input, not a sandbox. Do not feed it untrusted SQL.
- Existing graph data can be destroyed by `docker compose down -v`; see [Security](docs/SECURITY.md).

## Documentation

- [Documentation index](docs/README.md)
- [Delivery roadmap](docs/ROADMAP.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Development](docs/DEVELOPMENT.md)
- [Security](docs/SECURITY.md)
- [Runtime runbook](docs/RUNTIME.md)
- [Fixture reference](docs/FIXTURE.md)
- [Context catalog](docs/CONTEXT.md)
- [Phase 1 acceptance](docs/phase1-acceptance.md)
- [Phases 2–3 acceptance](docs/phase23-acceptance.md)
