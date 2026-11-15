# Security

Aftertrace is a local, single-operator development prototype. This document states the actual security properties of phases 1–3 and the gaps that block any production or multi-tenant use. It is a threat-model description, not a certification.

## Threat model

| Item | Current assumption |
| --- | --- |
| Deployment | One trusted host, one operator, loopback-only HydraDB ports. |
| Data | Synthetic fixture data only; no customer, production, personal, or regulated data. |
| Trusted code | The repository's Python modules, scripts, tests, and Compose file. |
| Untrusted input | Tool/contract metadata and any future tool output or memory; candidate SQL is trusted **internal** input today, not a sandboxed public input. |
| Protected asset | The HydraDB bearer token and the graph data behind it. |
| Out of scope | Internet-facing service, multi-tenancy, untrusted tenants, production warehouse connectors, backups, HA, and formal incident response. |

The runtime is not hardened against a hostile local user, a compromised Docker host, or a leaked token. Possession of the token grants graph access; scopes are namespacing, not authorization.

## Synthetic data only

- `app/fixture.py` generates an in-memory DuckDB warehouse from a seed. It makes no external calls, reads no external files, and contains no production records.
- Graph metadata is derived from that fixture schema plus declared lineage and tool descriptions. It does not contain scenario answers, causes, or repair labels.
- There are no data classification, redaction, retention, deletion, or tenant-isolation controls. Do not put production or personal data into this prototype.

## Credentials and secret handling

- `scripts/setup_runtime.py` creates `.env` with mode `0600` and a random 64-character hex token. It refuses to overwrite an existing file and never prints the token.
- `.env` is gitignored. `.env.example` contains placeholders only.
- Compose injects the token into the engine environment and writes it to `/state/token` with `umask 077`. The token therefore exists in `.env`, the container environment, and the named volume.
- The client sends `Authorization: Bearer <token>`. It rejects CRLF injection in the token/namespace headers and never logs the token in its sanitized errors.
- There is no secret manager, automatic rotation, access audit, or per-scope credential. After replacing the token in `.env`, recreate the engine with `docker compose up -d --force-recreate hydradb`, wait for readiness, and rerun the authenticated smoke check. A plain restart keeps the old Compose environment. Existing graph data remains in the named volume.
- Treat a token leak as full access to the graph. Remove the token from any shared logs, screenshots, shell history, or reports before sharing.

## Loopback plaintext limitation

- `compose.yaml` publishes query and admin ports only on `127.0.0.1` and sets `GRAPH_ALLOW_PLAINTEXT=true`.
- Bearer credentials and graph responses travel unencrypted over loopback. The token is also stored in plaintext in `.env` and `/state/token`.
- `hydra.py` rejects plaintext HTTP to non-loopback hosts and requires HTTPS for remote endpoints. No TLS termination, certificate management, or reverse proxy is included in this repository.
- Bolt is not published to the host. The query and admin ports must still be treated as sensitive local services.
- Anyone with access to the host account, Docker control, the `.env` file, or the `hydra-state` volume can obtain or use the credential.

## Host privilege boundary

- The one-shot `init-state` container runs as root only to create `/state/store` and `/state/cache`, recursively chown the volume to uid/gid `10001`, and set mode `700`.
- The engine data directory is owned by the unprivileged engine user (uid/gid `10001`). The Compose file does not add capabilities, but this is not a full container-hardening review.
- Docker/Compose control is effectively host-root access. Membership in the `docker` group is a privileged trust boundary, not an application-user boundary.
- The named volume survives restarts, but it is not backed up, replicated, or encrypted by this project.

## No unrestricted public SQL or application API

- The repository exposes no Aftertrace HTTP API, UI, or public SQL endpoint. The only interface is local CLI/Python code plus HydraDB's own authenticated query endpoint.
- HydraDB's Cypher endpoint is powerful. The application's graph layer builds queries from module constants, parameters, and app-owned IDs, but a caller with the token and transport can send other queries. Protect the token and keep the ports loopback-only.
- The fixture's `transform` argument is raw SQL inserted into a view definition. It is not parsed, path-restricted, resource-limited, or run in a general-purpose sandbox. DuckDB SQL can be powerful; **do not pass untrusted SQL or user-controlled strings to `warehouse()`**.
- Any repair workflow must keep transforms allowlisted and execute them in an isolated per-run workspace. The internal fixture transform argument is not that boundary, and no production sandbox is certified here.

## Trust of metadata, tool content, and memory

- `Tool` nodes contain descriptive metadata. The catalog layer does not execute them, and no planner or LLM consumes them in the documented phases.
- Contracts, tool descriptions, field details, and future evidence or memory content must be treated as untrusted data, not as instructions. A future agent must not let catalog or tool text change its authorization, evidence gates, or approval policy.
- Historical repair memory, once implemented, may suggest a diagnostic or candidate but must never satisfy current quantitative proof or bypass operator approval.
- Ingestion identifiers and query labels/relationship types come from module constants; values are parameterized. Keep it that way when extending the catalog.

## Multi-tenancy, availability, and backups

- There is no multi-tenant support. The default graph/namespace/cell and the bearer token are single-operator. Scopes isolate catalog owners logically, not by permission.
- There is no rate limiting, quota, audit log, usage accounting, or per-tenant deletion.
- There is no backup, restore, replication, failover, or high-availability mechanism. The only tested durability claim is that the named volume survives a container restart; host loss or volume deletion loses data.
- No recovery point objective, recovery time objective, or consistency guarantee is certified.

## Unsafe destructive reset

`docker compose down -v` deletes the `hydra-state` volume and **all graph data and the token file**, with no confirmation prompt, backup, or undo. Do not run it if you need the catalog or any future verified-repair memory.

Other deletion risks:

- `DETACH DELETE` and manual Cypher deletes are immediate and not reversible.
- The repository has no general scope-cleanup command. Live tests clean only their random scratch scopes/IDs; the runtime smoke script cleans marker-guarded scratch IDs.
- Re-ingestion after a version or scope change leaves old owner data in place; it does not garbage-collect it.
- Future fixture, incident, and memory resets must remain separate operations. A fixture reset must not silently erase verified memory or an in-flight incident.

Run destructive commands deliberately, verify the target scope/IDs, and keep a copy of anything you cannot regenerate.

## Responsible handling

- No formal security contact, response SLA, bug-bounty program, or disclosure policy is defined for this prototype. Do not assume one exists.
- Do not include tokens, `.env` contents, graph data, or other sensitive material in a report, issue, screenshot, or shared log.
- Use synthetic data only, keep the service on loopback, and stop it when not in use.
- If you find a security issue, report it privately to the repository maintainers through their normal private channel if one is available; otherwise omit exploitation details and sensitive data from public discussion. This document does not create a response commitment.

## Production hardening checklist (not implemented)

Every item below is a known gap, not a completed control. This is not a production-readiness claim.

| Control | Status |
| --- | --- |
| TLS termination for query/admin traffic and certificate management | Not implemented |
| Secret manager, automatic rotation, and access audit | Not implemented |
| Application authentication, authorization, and per-tenant isolation | Not implemented |
| Private network policy beyond loopback publishing | Not implemented |
| Non-root volume initialization or pre-provisioned ownership | Not implemented; a one-shot root init exists |
| `GRAPH_ALLOW_PLAINTEXT=false` with a real TLS deployment | Not implemented |
| Backup, restore, replication, failover, and tested RPO/RTO | Not implemented |
| Application rate limits, per-tenant quotas, and container CPU/memory caps | Not configured; the engine still has its own query budgets |
| Audit logging, monitoring, and alerting | Not implemented |
| Production-grade allowlisted transforms, isolated repair execution, and resource caps | Not implemented |
| Production-grade path traversal, symlink, and arbitrary-command protections for repair | Not implemented |
| Data retention, deletion, classification, and PII controls | Not implemented |
| Dependency/image scanning and a patch/update policy | Not implemented |
| Incident response and vulnerability disclosure policy | Not implemented |
| Multi-tenant billing, SSO, and public API protections | Not implemented; out of scope for the first release |

Use the local stack for development and synthetic demonstrations only.
