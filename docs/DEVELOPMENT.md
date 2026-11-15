# Development

This guide covers the local repository, setup, test commands, fixture and graph CLIs, repeatability, and cleanup cautions. Operational commands for starting, stopping, and checking the HydraDB runtime are in the [runtime runbook](RUNTIME.md); this page does not duplicate that runbook.

This guide documents the shipped phases 1–3 surface: runtime/transport, the synthetic fixture, and the context catalog. Investigation, approval, repair, memory, API/UI, and evaluation are not part of that documented shipped surface.

## Prerequisites

- Python 3.12+.
- Docker Engine with Compose v2.
- `curl` for the readiness check.
- Network access to pull the pinned HydraDB image on first start.

The only third-party Python dependency is `duckdb==2.0.0` from `requirements.txt`. Runtime setup and the transport use the standard library.

## Repository map

```text
aftertrace/
  app/
    config.py              # .env loading and HydraDB connection defaults
    fixture.py             # deterministic DuckDB warehouse, measures, invariants
    graph.py               # catalog construction, ingestion, bounded reads
  docs/
    ARCHITECTURE.md        # system, graph, lifecycle, transport, limits
    CONTEXT.md             # catalog usage and query interface
    DEVELOPMENT.md         # this guide
    FIXTURE.md             # fixture scenarios, transforms, invariants
    RUNTIME.md             # runtime setup, ports, persistence, smoke modes
    SECURITY.md            # local threat model and hardening gaps
    phase1-acceptance.md
    phase1-review.md
    phase23-acceptance.md
  scripts/
    check_fixture.py       # fixture measurements/invariants as JSON
    ingest_context.py      # seed a graph scope and print field context
    runtime_smoke.py       # live transport and persistence smoke
    setup_runtime.py       # create private .env without printing the token
  tests/
    test_fixture.py
    test_graph.py
    test_hydra.py
    test_live_transport.py
    test_transport.py
  compose.yaml             # pinned HydraDB engine and volume initialization
  hydra.py                 # HydraDB HTTP transport
  requirements.txt
  README.md
  .env.example
  phase.md                 # phased product/build plan
```

`data/receipts/` holds local, ignored JSON receipts from prior runs. It is runtime output, not source or benchmark data.

## Setup

From `aftertrace/`:

```sh
python3 -m venv .venv
.venv/bin/python scripts/setup_runtime.py
.venv/bin/pip install -r requirements.txt
docker compose up -d
```

Wait for readiness with a bounded check:

```sh
ready=0
for _ in $(seq 1 60); do
  if curl -fsS --max-time 2 -o /dev/null http://127.0.0.1:19091/readyz; then ready=1; break; fi
  sleep 1
done
[ "$ready" = 1 ] || { echo "HydraDB did not become ready"; exit 1; }
```

See [RUNTIME.md](RUNTIME.md) for ports, health endpoints, persistence checks, and safe stop/restart commands.

## Environment configuration

`app/config.py` reads `aftertrace/.env` if present and applies values with `os.environ.setdefault`, so a real environment variable wins over the file.

| Variable | Default | Required |
| --- | --- | --- |
| `HYDRA_TOKEN` | none | Yes; at least the server's accepted token length |
| `HYDRA_URL` | `http://127.0.0.1:18443` | No |
| `HYDRA_GRAPH` | `default` | No |
| `HYDRA_CELL` | `cell-0` | No |
| `HYDRA_NAMESPACE` | `default` | No |

`scripts/setup_runtime.py` creates `.env` with mode `0600`, a random 64-character hex token, and the local defaults. It refuses to overwrite an existing file and never prints the token. `.env` is gitignored. `.env.example` contains placeholders only. After changing the token in `.env`, run `docker compose up -d --force-recreate hydradb`, wait for readiness, and rerun the authenticated smoke check. A plain restart does not reload Compose environment values; the named volume and graph data are kept.

## Fixture CLI

`scripts/check_fixture.py` needs no HydraDB runtime. It prints one JSON object with `fixture_version`, `scenario`, `seed`, `candidate`, `metrics`, `checks`, and `all_passed`.

```sh
.venv/bin/python scripts/check_fixture.py --scenario duplicate --seed 7
.venv/bin/python scripts/check_fixture.py --scenario duplicate --seed 7 --candidate deduplicated
.venv/bin/python scripts/check_fixture.py --scenario healthy --seed 7
.venv/bin/python scripts/check_fixture.py --scenario stale --seed 7
.venv/bin/python scripts/check_fixture.py --scenario duplicate_heldout --seed 7 --candidate deduplicated
```

Scenarios are `healthy`, `duplicate`, `duplicate_heldout`, and `stale`. Candidates are `original` (the `BROKEN` transform) and `deduplicated` (`FIXED`). Seeds are `1..10000`. At seed 7, `duplicate` with `original` gives 154 rows and 83,914 cents with 6/11 checks; `deduplicated` gives 100 rows and 54,550 cents with 11/11. Results are deterministic for the same parameters.

The CLI's `--candidate` selects one of two built-in transforms; it does not accept arbitrary SQL. The Python `warehouse(..., transform=...)` argument accepts trusted internal SQL and is not a sandboxed execution surface. See [Security](SECURITY.md).

## Graph CLI

`scripts/ingest_context.py` requires the runtime and writes the healthy fixture catalog to the configured HydraDB graph.

```sh
.venv/bin/python scripts/ingest_context.py
.venv/bin/python scripts/ingest_context.py --scope local-check --field delivery_events.event_id
```

Defaults are scope `aftertrace` and field `delivery_fee_kpi.fee_cents`. The JSON output contains `ok`, `source`, `owner`, catalog `nodes`/`edges`, and the retrieved field context with contracts, tools, upstream fields, and counts. For the current healthy `fulfillment-v2` fixture, expect **46 catalog nodes and 63 edges** and owner `aftertrace:fulfillment-v2`.

Use `--scope` for experiments so the default catalog is not changed. Ingestion is repeatable: the same fixture/version/scope yields the same counts and field neighborhood. It does not ingest scenario labels or expected answers.

## Tests

Run local/unit tests from `aftertrace/`. The five phase 1–3 live tests skip unless explicitly enabled:

```sh
.venv/bin/python -m unittest discover -s tests -v
```

Run the current suite against the live runtime:

```sh
AFTERTRACE_LIVE_TEST=1 .venv/bin/python -m unittest discover -s tests -v
```

The phase 1–3 baseline is 41 tests (36 local plus 5 live). The command output is the current working tree's count. The live group includes real transport checks and graph tests. Live graph tests use random `graph-test-*` scopes; the live transport test uses scratch IDs `720000..720300`. They clean up their own data. Do not run live tests against a graph you are not willing to touch.

Run one module or one test:

```sh
.venv/bin/python -m unittest tests.test_fixture -v
.venv/bin/python -m unittest tests.test_graph.CatalogTests.test_identity_and_inputs -v
```

There is no lint, typecheck, coverage, or CI configuration in this repository. Do not treat the unittest suite as any of those.

## Repeatability, versions, and schema drift

Fixture versions live in `app/fixture.py`:

- fixture `fulfillment-v2`
- generator `generator-v2`
- contract `contract-v2`
- transform `transform-v2`
- invariants `invariants-v2.1`

The graph owner is `scope:VERSION`, so the fixture version is part of every catalog ID. Changing the fixture schema or declared lineage changes the catalog fingerprint. Under the same scope/version, re-ingestion fails with a schema-change error instead of mixing old and new metadata. Bump the fixture `VERSION` intentionally, or use a new `--scope`; changing only a sub-version does not bypass the manifest check.

Bumping `VERSION` (or changing scope) creates a new owner and new IDs; it does **not** delete the old owner's nodes. Treat old catalogs as separate data to clean up deliberately.

Pinning:

- `requirements.txt` pins `duckdb==2.0.0`.
- `compose.yaml` pins the HydraDB image by digest for both services.
- Python standard library covers the transport and runtime scripts.
- There is no lockfile, automated dependency update, image scan, or CI job.

## Change and test workflow

1. Read [Architecture](ARCHITECTURE.md) and [Fixture](FIXTURE.md) before changing data shapes or lineage.
2. Edit the fixture/transform/invariants and bump the relevant version strings if the contract changes.
3. Run the affected fixture checks and the full local unittest suite.
4. Start or reuse the local runtime if live behavior changed; run the live suite with `AFTERTRACE_LIVE_TEST=1`.
5. Seed a scratch scope with `scripts/ingest_context.py --scope ...` and inspect the JSON counts/field context.
6. Clean up only the scratch data you created, then update the relevant docs or acceptance notes.

Keep generated `.env`, `data/` output, and runtime artifacts out of commits.

## Scope and data cleanup cautions

- No general scope-deletion tool exists. Live tests clean their own scopes/IDs; the runtime smoke script cleans marker-guarded scratch IDs.
- Manual graph deletion must be deliberate and ID-specific. Never delete by a broad label or owner unless you know every matching row belongs to your scratch scope.
- Re-ingestion does not remove nodes from an older scope or fixture version.
- `docker compose down -v` deletes the `hydra-state` volume and all graph data, including any future memory. There is no backup or confirmation step. See [Security](SECURITY.md).
- Do not run live tests or ingestion against shared or production data. This repository is a local synthetic prototype.

## Current limitations

- Synthetic fixture only, with one incident family and 100 shipments.
- Declared lineage for the owned SQL, not a general SQL lineage parser.
- Client-side bounded search, not scalable full-text retrieval.
- Single-operator ingestion; no transactions, distributed lock, or multi-query snapshot consistency.
- The documented shipped surface does not include investigation, evidence gates, approval, repair execution, verification orchestration, memory, API/UI, or evaluation.
- Local loopback plaintext runtime with no production security or operations guarantees.

See [Architecture](ARCHITECTURE.md) for tradeoffs and [Security](SECURITY.md) for the threat model and hardening gaps.
