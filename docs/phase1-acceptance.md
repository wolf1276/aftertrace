# Phase 1 acceptance receipt

Completed against the self-hosted Docker runtime in this workspace.

## Runtime

- Image: `ghcr.io/hydra-db/hydradb@sha256:ab71d651fefee13ebb23eb56d72316065bdca563ff7587442e07be663f2bf880`.
- Engine build commit: `916637477f3f34766b4905b270bd4292109d77e6` (reported by runtime logs).
- Query: `http://127.0.0.1:18443`; admin: `http://127.0.0.1:19091`.
- Namespace/graph/cell: `default` / `default` / `cell-0`.
- Durable named volume: Compose `hydra-state`.
- Unprivileged engine uid/gid `10001`; one-shot root volume initialization fixes mounted-volume ownership.
- Token generated locally, private `.env`, not included in this receipt.

## Checks performed by the head agent

```sh
cd aftertrace
AFTERTRACE_LIVE_TEST=1 .venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/runtime_smoke.py
.venv/bin/python scripts/runtime_smoke.py --write-persistence
docker compose restart hydradb
# Wait for the admin readiness endpoint to return HTTP 200.
.venv/bin/python scripts/runtime_smoke.py --check-persistence
.venv/bin/python scripts/runtime_smoke.py --cleanup-persistence
```

Results:

- 17 unit/integration tests passed, including two actual database tests.
- Live 301-row scan traversed the default 256-row page boundary without missing rows.
- Repeated MERGE produced one relationship, not duplicates.
- Actual vertex ID, list, null, and property values decoded correctly.
- Wrong authentication and invalid Cypher failed closed.
- Mocked malformed responses, HTTP failures, timeout, changed columns, missing envelopes, and failed second pages raised sanitized errors without retries or partial results.
- Bearer-token redirect forwarding is disabled.
- Six smoke checks passed and scratch records were removed.
- Persistence marker written before an actual `docker compose restart hydradb` was read afterwards; marker cleanup succeeded.
- Raw JSON smoke/persistence receipts are local at `data/receipts/phase1-*.json` (ignored runtime output).

## Restart defect discovered and addressed

The pinned runtime generates HTTP query IDs from a process counter. After restart those IDs can collide with durable mutation identities, causing HTTP 409 `mutation_conflict` even though existing data is intact. The client now supplies a fresh UUID-based `query_id` for each new query and preserves the server query ID during pagination. A regression test checks uniqueness. The actual restart/read/write/cleanup flow passed after this fix.

## Delegation and review

OpenCode was assigned exclusive ownership of `scripts/runtime_smoke.py`, `docs/RUNTIME.md`, and `docs/phase1-review.md`. Head agent owns Compose, transport, configuration, transport tests, this acceptance receipt, and root planning files. OpenCode event logs are local in `/tmp/aftertrace-agents/phase1-opencode-2.jsonl`; no overlapping file ownership was assigned.

## Limits

This establishes a local single-node authenticated runtime, not a deployed production service. TLS, production secret management, multi-node consistency, backup recovery, and application-level investigation/repair are not certified by Phase 1. The engine remains running locally. No landing page or marketing work is included.
