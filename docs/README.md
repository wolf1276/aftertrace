# Documentation

Aftertrace is a data-incident context workbench under active development. The current release provides executable synthetic incident fixtures, invariant verification, and a self-hosted HydraDB context catalog. The investigation and approved-repair workflow is not shipped yet.

## Start here

| Document | What it covers |
| --- | --- |
| [Project overview](../README.md) | Product purpose, current capabilities, local quickstart |
| [Architecture](ARCHITECTURE.md) | Components, data flows, graph model, lifecycle, trust boundaries, tradeoffs |
| [Development](DEVELOPMENT.md) | Environment setup, module map, tests, fixture and graph workflows |
| [Runtime operations](RUNTIME.md) | Engine startup, credentials, persistence, restart checks, safe shutdown |
| [Security](SECURITY.md) | Threat model, trusted inputs, local-only limitations, production hardening gaps |
| [Roadmap](ROADMAP.md) | Delivered capabilities and remaining release gates |

## Implementation references

- [Synthetic fulfillment fixture](FIXTURE.md): generation, scenarios, transforms, diagnostics, and 11 invariants.
- [Context catalog](CONTEXT.md): query interface, lineage, identity, ingestion, isolation, and budgets.

## Verification records

These records describe checks performed against a specific local environment. They are engineering evidence, not availability commitments, production certifications, or learning benchmarks.

- [Runtime acceptance](phase1-acceptance.md)
- [Fixture and context acceptance](phase23-acceptance.md)
- [Transport implementation review](phase1-review.md)

For exact behavior, refer to the [implementation](../app/) and [tests](../tests/). If a roadmap item and a running command differ, the roadmap is not evidence that the feature exists.
