# Runtime operations

Local, authenticated, durable HydraDB for Aftertrace. The stack is `compose.yaml`
and pins `ghcr.io/hydra-db/hydradb@sha256:ab71d651fefee13ebb23eb56d72316065bdca563ff7587442e07be663f2bf880`
for both `init-state` and `hydradb`.

## Prerequisites

- Docker Engine with Compose v2.
- Python 3.12+. From the repository root, create the virtualenv with
  `python3 -m venv .venv`. Runtime smoke checks use only the standard library;
  fixture and context commands also need `pip install -r requirements.txt`.

## Configure the secret

Use the setup script. It creates `.env` with mode `0600`, a random 64-character
hex token, and the local endpoint defaults, and it never displays the token:

```sh
.venv/bin/python scripts/setup_runtime.py
```

It refuses to overwrite an existing `.env`. If you create the file by hand,
write it under `umask 077`, keep mode `600`, and include all five values:

```text
HYDRA_TOKEN=<at least 32 characters>
HYDRA_URL=http://127.0.0.1:18443
HYDRA_GRAPH=default
HYDRA_CELL=cell-0
HYDRA_NAMESPACE=default
```

`.env.example` contains placeholders only. Never commit `.env` or print the
token. To rotate `HYDRA_TOKEN`, update the private `.env`, then run
`docker compose up -d --force-recreate hydradb` and rerun the authenticated smoke
check. A plain `restart` does not reload changed Compose environment variables.
Existing graph data is kept in the named volume.

## Start

```sh
docker compose up -d
curl -fsS --max-time 2 --retry 20 --retry-delay 1 --retry-all-errors \
  -o /dev/null http://127.0.0.1:19091/readyz
curl -fsS http://127.0.0.1:18443/healthz
```

`init-state` runs first: it creates `/state/store` and `/state/cache` and
chowns them to uid/gid `10001`. `hydradb` then writes `/state/token` with
`umask 077` and starts `graph-node`.

### Ports and health checks

| Purpose | Host address | Container port |
| --- | --- | --- |
| Query API, `/healthz` | `127.0.0.1:18443` | `8443` |
| Admin, `/readyz`, `/metrics` | `127.0.0.1:19091` | `9090` |
| Bolt | not published | `7687` |

The endpoints are on different ports and are not interchangeable:

- `GET http://127.0.0.1:18443/healthz` returns `200` and `{"status":"ok"}`.
- `GET http://127.0.0.1:19091/readyz` returns `200` with an **empty body**.
  Check the status code, not the body.
- `GET http://127.0.0.1:19091/healthz` returns `404`; `/metrics` is admin-only.

A reachable health endpoint does not prove authenticated database access. Run:

```sh
.venv/bin/python scripts/runtime_smoke.py
```

This loads credentials from the environment/private `.env`, performs real
authenticated queries, and never passes the token as a shell argument.
Avoid `docker compose config` without `--quiet`: rendered configuration includes
expanded environment values. Docker administrators can inspect container secrets;
loopback networking is not a defense against an untrusted local administrator.

## Named-volume persistence

The `hydra-state` named volume holds the durable object store
(`/state/store`), the cache (`/state/cache`), and the token file
(`/state/token`). Container restarts do not delete it.

- `docker compose stop hydradb` / `docker compose start hydradb` keep the volume.
- `docker compose restart hydradb` keeps the volume.
- `docker compose down` keeps the volume.
- `docker compose down -v` **deletes the volume and all graph data.** This is
  the reset command; use it deliberately.

After any start, wait for `/readyz` before sending queries.

## Non-destructive smoke test

From `aftertrace/`:

```sh
.venv/bin/python scripts/runtime_smoke.py
```

The script writes only application-owned scratch IDs `880000001`–`880000003`
with relationship type `PHASE1_SMOKE` and marker property
`aftertrace-phase1-smoke`. It re-runs an idempotent `MERGE` to prove edges do
not duplicate, asserts exact decoded `vertex_id`, list, null, and property
values, and deletes the scratch nodes in a `finally` block. Cleanup is guarded
by the marker property, so it cannot delete unrelated application metadata.

It prints one JSON receipt with `ok`, `mode`, `elapsed_seconds`, `operations`,
and `checks`; exit status is `0` on success and `1` on failure. It never prints
the token, endpoint credentials, or `.env` contents.

### Restart-persistence check

The persistence marker uses separate IDs `880000900`/`880000901`, relationship
type `PHASE1_PERSIST`, and marker `aftertrace-phase1-persistence`:

```sh
.venv/bin/python scripts/runtime_smoke.py --write-persistence
docker compose restart hydradb
curl -fsS --max-time 2 --retry 20 --retry-delay 1 --retry-all-errors \
  -o /dev/null http://127.0.0.1:19091/readyz
.venv/bin/python scripts/runtime_smoke.py --check-persistence
.venv/bin/python scripts/runtime_smoke.py --cleanup-persistence
```

`--check-persistence` only reads; it fails if the marker is missing. It proves
restart survival only when run after a real restart. `--cleanup-persistence`
deletes only the two marker IDs and only where the marker property matches.

Pinned-engine behavior after restart: server-generated HTTP query IDs restart
at `http-query-1` and can collide with durable mutation identities, producing
HTTP 409 `mutation_conflict`. The current client sends an
`aftertrace-<uuid>` query ID for each new query and keeps the server's ID for
pagination. Do not replace that with a counter.

## Safe stop and restart

```sh
docker compose ps
docker compose logs --tail=100 hydradb
docker compose stop hydradb     # or: restart hydradb
docker compose start hydradb
```

Do not use `down -v` during a persistence check or after collecting data you
want to keep. Do not delete the `hydra-state` volume manually.

## Secret handling

- The bearer token lives only in `aftertrace/.env`, the Compose environment, and
  `/state/token` inside the volume (created with `umask 077`).
- `.env` is gitignored. Keep it mode `600`; do not echo it in logs, screenshots,
  or shell history. `scripts/setup_runtime.py` creates it without printing it.
- HydraDB rejects missing or wrong tokens with `401 unauthenticated`; the client
  raises a sanitized error. There is no mock fallback.
- Smoke receipts contain IDs, operation names, check results, and timing only.

## Local-only plaintext limitation

`compose.yaml` publishes ports only on `127.0.0.1` and sets
`GRAPH_ALLOW_PLAINTEXT=true`. Bearer credentials therefore travel in plaintext
over loopback, and the token is stored in plaintext in `.env` and
`/state/token`. This is for local development only.

For any non-loopback deployment:

- terminate TLS in front of the query port and use `https://` endpoints;
  `hydra.py` rejects plaintext HTTP to non-loopback hosts,
- keep the query and admin ports private; expose only the application surface,
- move tokens to a secret manager and never bake them into images or frontend
  assets.

## Verification status

The [runtime acceptance receipt](phase1-acceptance.md) records authenticated
write/read/delete, 301-row pagination, and persistence across an actual container
restart. The [fixture/context acceptance receipt](phase23-acceptance.md) records
the complete 41-test suite and actual graph ingestion.

These are local single-node checks—not backup restoration, multi-node failover,
production TLS, load testing, or a production-readiness certification.
