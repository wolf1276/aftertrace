# Delivery roadmap

This roadmap separates delivered implementation from planned product behavior. It is not a release-date commitment. The detailed engineering checklist is in [phase.md](../phase.md).

## Delivered

### Runtime foundation

- Digest-pinned, self-hosted HydraDB with authenticated queries and persistent local storage.
- Parameterized HTTP client with sanitized errors, disabled credential redirects, consuming-cursor pagination, and bookmark forwarding.
- Live write/read/delete, pagination, and container-restart persistence checks.

### Executable incident fixtures

- Deterministic DuckDB fulfillment pipeline with healthy, duplicate, held-out identifier/partition, and missing-shipment scenarios.
- Measured daily fees, source reconciliation, duplicate/null rates, and a misleading non-critical freshness signal.
- Eleven invariants, including shipment completeness and preservation of accepted event contents.

### Context catalog

- Actual schema introspection; declared dataset and field lineage.
- Field contracts and diagnostic capability registry in HydraDB.
- Scoped identity checks, repeatable ingestion, pending/ready publication, bounded retrieval, and recovery tests.
- Actual fixture catalog: 46 nodes and 63 edges. This describes the fixture, not system capacity.

## Next: evidence-backed investigation

**Outcome:** a broken metric produces a reproducible diagnosis supported by current measurements and graph context; a healthy control does not produce a false incident.

Release gates:
- Typed incident state, hypotheses, evidence provenance, citations, and durable local recovery.
- Deterministic diagnostic dispatch with no unrestricted SQL or arbitrary command tool.
- Confirmation requires current quantitative evidence tied to a field in the retrieved graph.
- Explicit healthy, inconclusive, budget-exhausted, and dependency-failure outcomes.
- Tests reject fabricated citations, irrelevant measurements, and unknown fields.

A deterministic planner comes first. LLM orchestration is optional and must be labeled accurately if added.

## Next: operator-approved repair

**Outcome:** an operator approves a particular candidate, and only an isolated execution with all required checks passing can be recorded as verified.

Release gates:
- Real candidate diff and content hash.
- Approval bound to incident, candidate hash, and compatible fixture version.
- Allowlisted repair target and isolated temporary workspace/database.
- Full invariant verification, including non-regression checks rather than headline recovery alone.
- Explicit rejection/failure artifacts, timeout and cancellation handling, concurrent-approval tests, and cleanup.

The current internal fixture transform argument is not this approval or isolation service.

## Subsequent releases

| Capability | Acceptance condition |
| --- | --- |
| Verified repair memory | Only durably verified, compatible outcomes are retrieved; historical repairs never replace current evidence |
| API and workbench | Browser flow exposes real investigation state, evidence, approval, diff, checks, and writeback failures |
| Learning evaluation | Frozen training/held-out splits, fair cold/graph/flat-memory comparisons, raw receipts, and failures retained in the denominator |
| Deployment | Private engine ports, HTTPS app surface, protected mutations, secret management, restart recovery, and reproducible installation |

No learning or resolution-speed improvement has been established. Incident variants in the fixture are not customer validation or evidence of broad diagnostic generalization.

## Explicitly excluded

A marketing site, landing page, billing, multi-tenant SaaS, unrestricted production repairs, and automatic remote repair publication are outside the current implementation scope.
