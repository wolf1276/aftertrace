# Aftertrace — phased build and delivery plan

## 1. Objective

Build a new HydraDB-native data reliability workbench from scratch.

**Pitch:** Aftertrace turns verified incident repairs into a connected context layer, helping the next investigation find relevant evidence and tools without trusting yesterday's answer blindly.

**Primary track:** agent context layer. HydraDB connects assets, contracts, tools, evidence, and verified repairs so investigations retrieve a small, relevant context subgraph.

**Secondary track:** continual improvement, only if experiments demonstrate improvement over training checkpoints on held-out incidents. Memory retrieval is not model training; describe the mechanism accurately.

**Initial buyer hypothesis:** small data/platform teams handling recurring semantic pipeline incidents. Validate this hypothesis rather than presenting it as established demand.

## 2. Current state — verified versus planned

- [x] Separate project directory: `aftertrace/`.
- [x] Initial product contract: `aftertrace/README.md`.
- [x] Original standard-library HTTP client: `aftertrace/hydra.py`.
- [x] Forty-one passing unit/integration tests across `aftertrace/tests/`, including real HydraDB checks.
- [x] Initial reading of the reference architecture, domain models, and dashboard.
- [ ] Complete reference source review. File inventory exists; full review is not complete.
- [x] Live, authenticated HydraDB write/read/delete, pagination, and actual restart-persistence tests.
- [x] Metadata ingestion and bounded graph/contract/tool retrieval: 46 nodes, 63 edges.
- [x] Synthetic warehouse, healthy/incident/held-out fixtures, and 11 invariants.
- [ ] Investigation, approval, repair, and verification engine.
- [ ] API and frontend.
- [ ] Verified-memory retrieval and learning benchmark.
- [ ] Deployment, customer validation, and submission assets.

Passing transport unit tests do **not** establish database connectivity or end-to-end correctness. No measured learning result exists yet.

This plan replaces the migration approach in root `MIGRATION.md`: the deliverable is a new implementation, not provider replacement inside the reference repository. That document remains historical planning material.

## 3. Scope and non-goals

### Must ship

1. Self-hosted HydraDB with durable storage and authenticated queries.
2. Original fulfillment pipeline fixture with healthy and broken variants.
3. Dataset and field lineage, contracts, diagnostic tool relationships, and evidence provenance stored in the graph.
4. Investigation with machine-enforced evidence requirements.
5. Explicit operator approval before running a candidate repair.
6. Isolated candidate execution and full invariant verification.
7. Only verified repairs eligible for successful repair-memory retrieval.
8. A usable command center showing actual runtime results and failure states.
9. Reproducible evaluation comparing context and memory strategies.
10. Deployment/runbook, demo walkthrough, and truthful customer-facing pitch.

### Out of scope for the first release

- Arbitrary production warehouse mutation or unrestricted SQL execution.
- Automatic deployment of repairs, remote Git pushes, or PR publication.
- Multi-tenant SaaS, billing, SSO, and connector marketplace.
- Fine-tuning, autonomous self-modifying agents, or fabricated accuracy curves.
- Copying the reference repository's implementation, branding, assets, fixtures, or benchmark receipts.

General workflow ideas can inform the design. Independently write code and visual assets. Do not claim a clean-room process after reviewing source. If any third-party implementation is later reused, check its terms and retain required notices. Check hackathon disclosure rules separately.

## 4. Target architecture

```text
Browser command center
          |
          v
Aftertrace API + incident state machine
          |
          +--> bounded context retrieval --> self-hosted HydraDB
          |                                  assets / fields / contracts
          |                                  tool capabilities / provenance
          |                                  verified repair memory
          |
          +--> deterministic diagnostics --> isolated DuckDB fixture
          |
          +--> optional LLM investigation planner
          |    chooses tools; cannot manufacture evidence
          |
          +--> approved candidate --> isolated rebuild + invariants
                                      |
                                      v
                               verified repair record
                                      |
                                      v
                                HydraDB writeback
```

### Proposed implementation choices

- Python backend with FastAPI, Pydantic, and DuckDB.
- Existing standard-library HydraDB HTTP transport, extended only when required.
- React + TypeScript frontend with a custom SVG lineage view initially; add a graph library only if interaction needs justify it.
- Server-side credentials only.
- Local incident records for crash recovery; HydraDB is the authoritative context/memory service. Choose one explicit persistence format and avoid competing sources of truth.
- SSE full-state snapshots with reconnect support, or simple polling if that is sufficient for the first vertical slice.
- Deterministic diagnostic mode for reproducible demos; label it explicitly. LLM mode must expose its actual provider/configuration and not pretend scripted decisions are autonomous.

### Intended project layout

```text
aftertrace/
  hydra.py                  # existing transport; move only if imports need it
  README.md
  pyproject.toml
  .env.example
  app/
    api.py
    config.py
    models.py
    graph.py
    investigation.py
    repair.py
    persistence.py
  fixtures/
    fulfillment/
      generate.py
      transforms/
      contracts.json
  tests/
  evals/
    scenarios.py
    run.py
    results/
  web/
  scripts/
  docs/
```

The layout is a target, not a requirement to create empty modules. Keep the smallest complete implementation.

## 5. Graph and workflow contracts

### Nodes

| Node | Minimum properties |
| --- | --- |
| Dataset | stable key, name, layer, schema version |
| Field | dataset key, name, type, contract version |
| Contract | meaning, units, uniqueness/nullability constraints, version |
| Tool | name, supported operation, input schema/version |
| Incident | run ID, fixture version, state, affected asset |
| Evidence | ID, producing tool, timestamp, payload reference, content hash |
| Repair | ID, candidate hash, verification status, compatible versions |
| Verification | suite version, checks passed/failed, result artifact hash |

### Directed relationships

- `Dataset -[:HAS_FIELD]-> Field`
- `Dataset -[:FEEDS]-> Dataset`
- `Field -[:DERIVES]-> Field`
- `Field -[:GOVERNED_BY]-> Contract`
- `Tool -[:INSPECTS]-> Field`
- `Incident -[:AFFECTS]-> Dataset`
- `Incident -[:HAS_EVIDENCE]-> Evidence`
- `Evidence -[:PRODUCED_BY]-> Tool`
- `Incident -[:HAS_REPAIR]-> Repair`
- `Repair -[:TARGETS]-> Field`
- `Repair -[:VERIFIED_BY]-> Verification`

Assign stable numeric HydraDB IDs from an application-owned registry or deterministic mapping with collision detection. Never use Python's process-randomized `hash()` for persistent identity. Store human-readable stable keys as properties.

### State transitions

```text
NEW -> INVESTIGATING -> AWAITING_APPROVAL -> VERIFYING -> VERIFIED
                   \-> NO_INCIDENT
                   \-> INCONCLUSIVE
Any active stage -> FAILED
VERIFYING -> REJECTED
VERIFIED -> memory writeback pending -> memory writeback complete
```

Failed writeback does not erase successful verification. Rejected candidates do not become successful memory examples. Authorization binds to a specific candidate hash; changing the candidate invalidates approval.

### Confirmation gate

A confirmed cause requires all of:

- The blamed field belongs to the graph neighborhood actually retrieved.
- Current contract/lineage evidence has recorded HydraDB provenance.
- Current quantitative measurements directly address the blamed field.
- Every citation resolves to evidence created by deterministic tools in this run.
- A competing explanation has been checked when applicable.

Historical memory can suggest a diagnostic or candidate, but cannot satisfy current quantitative proof by itself. Healthy/no-incident conclusions also require current quantitative checks.

## Phase 0 — lock the independent design and review

**Goal:** understand useful behaviors without copying implementation.

Tasks:
- [ ] Read the remaining reference backend, frontend, fixtures, tests, and evaluation source in manageable batches.
- [ ] Record reviewed paths and general behavioral findings; do not claim the full review until complete.
- [ ] Extract a small behavioral requirements checklist: evidence, approval, verification, recovery, and UI states.
- [ ] Define a new fulfillment incident narrative, data schema, invariants, and visual direction.
- [ ] Confirm current event track, eligibility, deadline, and disclosure requirements from official material.
- [ ] Freeze first-release scope and distinguish required work from stretch goals.

**Deliverables:** source-review checklist, original product specification, confirmed event checklist.

**Exit gate:** implementation can be explained without relying on the reference project's file structure, UI assets, or exact fixture.

## Phase 1 — prove HydraDB runtime and transport

**Status:** complete for local single-node development. Acceptance receipt: `aftertrace/docs/phase1-acceptance.md`. OpenCode owns the runtime smoke script/runbook/review; head agent owns runtime integration and transport. Production deployment remains a later phase.

**Depends on:** Phase 0 scope decisions.

Tasks:
- [x] Read the engine's startup/contributor instructions and pin the tested revision/image digest.
- [x] Start one self-hosted instance with authentication and durable storage.
- [x] Document endpoint, graph, cell, health/readiness ports, and secret configuration.
- [x] Run an authenticated write/read/delete smoke check in an app-owned test ID range.
- [x] Confirm data survives an actual container restart.
- [x] Exercise null/list decoding and vertex IDs against actual responses.
- [x] Add sanitized handling for HTTP failures, malformed JSON/results, and timeouts.
- [x] Test query errors, missing result envelopes, real pagination, and failed page fetches.
- [x] Respect non-retryable consuming cursors; fail the whole scan without returning partial rows.
- [x] Use parameters, explicit scope, bounded query forms, and idempotent MERGE writes.
- [x] Carry successful query bookmarks into subsequent requests; test forwarding.
- [x] Supply unique client query IDs to prevent pinned-engine mutation conflicts after restart.

**Deliverables:** startup script/runbook, `.env.example`, integration smoke test, runtime receipt.

**Exit gate:** authenticated graph write/read succeeds, restart persistence succeeds, and unavailable HydraDB produces an explicit error—not mock success.

## Phase 2 — build an original executable fixture

**Status:** complete. See `aftertrace/docs/phase23-acceptance.md` and `aftertrace/docs/FIXTURE.md`.

**Depends on:** Phase 0; can proceed alongside Phase 1.

Tasks:
- [x] Generate deterministic synthetic shipment/delivery data; omit a separate orders subsystem as unnecessary for this slice.
- [x] Build raw -> normalized events -> shipment facts -> operational KPI transforms.
- [x] Define documented field contracts independently of scenario answers.
- [x] Implement the initial duplicate-event incident and a healthy control.
- [x] Introduce held-out variants with different event identifiers and source partitions.
- [x] Add a non-critical stale heartbeat distractor disconnected from fee lineage.
- [x] Compute actual KPI history, row counts, duplicate/null rates, and reconciliation.
- [x] Verify 11 invariants including completeness, identity/content conservation, required values, and unaffected partitions. This fixture models one delivery per shipment, not a multi-event lifecycle.
- [x] Version fixture generation, contracts, transforms, and invariant suite.
- [x] Keep scenario labels/expected causes out of warehouse and graph metadata; future tools must not expose trusted generator/verifier source.

**Deliverables:** repeatable fixture generator, SQL transforms, baseline measurements, invariant tests.

**Exit gate:** healthy fixture passes all invariants; broken fixture fails the intended checks deterministically; expected answers are not encoded in agent-facing metadata.

## Phase 3 — ingest the context graph

**Status:** complete against the real self-hosted engine. Actual fixture: 46 nodes, 63 edges; repeat ingestion identical. See `aftertrace/docs/CONTEXT.md` and `aftertrace/docs/phase23-acceptance.md`.

**Depends on:** Phases 1 and 2.

Tasks:
- [x] Introspect dataset and field schemas from the running fixture.
- [x] Ingest contracts and explicitly declared dataset/field lineage.
- [x] Register diagnostic tools and the fields they inspect (execution is Phase 4).
- [x] Write labels/properties before edges according to the tested HydraDB dialect.
- [x] Make ingestion repeatable without duplicate relationships.
- [x] Implement asset lookup, bounded upstream traversal, contract lookup, and relevant-tool retrieval.
- [x] Apply explicit result/context budgets and stable ordering.
- [x] Return query provenance and retrieval counts for the UI/evaluations.
- [x] Test missing scopes/assets, schema drift, cycles, empty neighborhoods, ID collisions, budgets, and recovery after interrupted edge ingestion.

**Deliverables:** ingestion command, graph query layer, graph integration tests.

**Exit gate:** two-hop field lineage and related diagnostic tools come from actual HydraDB results; re-ingestion preserves correct node/edge counts.

## Phase 4 — evidence-backed investigation

**Depends on:** Phases 2 and 3.

Tasks:
- [ ] Define typed incidents, hypotheses, evidence records, citations, and transitions.
- [ ] Implement deterministic profiling and contract checks.
- [ ] Restrict warehouse query tools to vetted read-only operations; avoid regex-only SQL security.
- [ ] Persist evidence payloads and provenance before presenting them as facts.
- [ ] Implement the confirmation/no-incident gates above.
- [ ] Build a reproducible deterministic planner first.
- [ ] Add bounded LLM tool selection if needed, with call/token/time limits.
- [ ] Treat tool output, metadata, and memory as untrusted content—not privileged instructions.
- [ ] Expose explicit inconclusive, tool failure, budget exhaustion, and graph-unavailable outcomes.
- [ ] Add tests for fabricated citations, unrelated measurements, unknown fields, and healthy controls.

**Deliverables:** investigation service, evidence artifacts, adversarial gate tests.

**Exit gate:** an actual broken fixture yields a reproducible evidence-backed diagnosis; healthy data does not trigger an invented repair; invalid citations cannot advance state.

## Phase 5 — approval, isolated repair, and verification

**Depends on:** Phase 4.

Tasks:
- [ ] Generate candidates restricted to allowlisted fixture transforms.
- [ ] Compute a real diff and content hash from candidate/original files.
- [ ] Bind explicit operator approval to incident ID, candidate hash, and fixture version.
- [ ] Execute approved candidates only in per-run temporary workspaces/databases.
- [ ] Prevent path traversal, symlink escape, arbitrary commands, and test-suite edits.
- [ ] Rebuild affected pipeline outputs and run the full invariant suite.
- [ ] Require both KPI recovery and non-regression checks; headline recovery alone is insufficient.
- [ ] Persist rejected candidates and check failures for audit, without promoting them to successful memory.
- [ ] Ensure exceptions/cancellation cannot modify the original fixture or leave the incident falsely verified.
- [ ] Test bad repairs, stale approval, concurrent approval, timeouts, and cleanup.

**Deliverables:** candidate diff, approval endpoint/service, isolated execution, machine-readable verification report.

**Exit gate:** a valid approved candidate passes every required check; invalid or unapproved candidates never become verified; original files remain intact.

## Phase 6 — verified repair memory and context selection

**Depends on:** Phases 3–5.

Tasks:
- [ ] Write incident/evidence/repair/verification relationships with retry-safe IDs.
- [ ] Mark memory retrieval eligibility only after verification artifacts are durably recorded.
- [ ] Handle partial graph writes so incomplete memory cannot appear successful.
- [ ] Retrieve compatible verified repairs through target fields and bounded lineage neighborhoods.
- [ ] Filter fixture, schema, contract, tool, and verification-suite compatibility.
- [ ] Rank deterministically and cap retrieved records/context size.
- [ ] Explain why each memory matched; expose source incident and verification evidence.
- [ ] Run current diagnostics before suggesting or approving reuse.
- [ ] Test irrelevant memory, contradictory memory, incompatible versions, and failed writeback.
- [ ] Separate fixture reset, incident reset, and explicit memory deletion operations.

**Deliverables:** graph writeback, verified-memory retrieval, provenance explanations, isolation tests.

**Exit gate:** one verified repair becomes retrievable for a compatible new incident, while rejected/unverified examples do not; reuse never bypasses current evidence or approval.

## Phase 7 — API and original command-center UI

**Depends on:** contracts from Phase 4; complete integration after Phase 6.

### API surface

| Method/path | Purpose |
| --- | --- |
| `GET /api/health` | Real dependency readiness without secret disclosure |
| `GET /api/context` | Retrieved lineage/contracts/tool neighborhood |
| `GET /api/metrics` | Actual fixture KPI and measurements |
| `POST /api/incidents` | Start investigation with validated input |
| `GET /api/incidents/{id}` | Snapshot/recovery |
| `GET /api/incidents/{id}/events` | Optional SSE snapshots |
| `POST /api/incidents/{id}/approve` | Approve exact candidate hash |
| `GET /api/memory` | Verified examples with provenance |
| `GET /api/evaluations` | Recorded experiment results, never generated claims |

### UI tasks

- [ ] Choose an original visual system: dark operational workspace, restrained amber alerts, teal verified states, readable typography.
- [ ] Build asset/incident navigation, KPI summary, lineage workspace, and evidence inspector.
- [ ] Distinguish hypotheses, measured facts, suggested memory, approval, and verified outcomes visually.
- [ ] Show retrieved context size, selected tools, matching memory, and provenance.
- [ ] Render the actual candidate diff and invariant results.
- [ ] Support loading, disconnected, empty, healthy, inconclusive, rejected, verified, and writeback-pending states.
- [ ] Require clear approval action; disable repeated requests while processing.
- [ ] Add keyboard access, focus states, accessible status text, responsive layout, and non-color status labels.
- [ ] Never silently substitute demo data when services fail. Any preview mode must be explicitly watermarked.
- [ ] Test refresh/reconnect, API errors, repeated clicks, and small-screen behavior.

**Deliverables:** working UI and API contracts, frontend checks, end-to-end user-flow test.

**Exit gate:** a browser user can inspect a live incident, review evidence/diff, approve a candidate, inspect verification, and see truthful memory-writeback status.

## Phase 8 — prove whether memory and graph context help

**Depends on:** Phase 6; can run independently of UI polish.

### Experiment arms

1. **Cold graph:** contracts, lineage, and tools; no prior repair memory.
2. **Graph memory:** identical graph context plus compatible verified training repairs.
3. **Flat memory:** same training records and comparable context budget, without relationship-aware retrieval.
4. **Optional no-graph ablation:** fixture/schema access without graph context, with fair alternative evidence gates. Do not make failure inevitable by requiring unavailable graph citations.

### Protocol

- [ ] Predeclare scenario split, budgets, scoring rules, and primary metric.
- [ ] Train/accumulate verified memory on training incidents only.
- [ ] Freeze snapshots at sequential training checkpoints.
- [ ] Evaluate each snapshot against the same held-out suite without writing held-out outcomes back into training memory.
- [ ] Keep the model, provider settings, tool permissions, and budgets comparable across arms.
- [ ] Isolate graph scopes and warehouse state per arm/trial.
- [ ] Include healthy controls, distractors, incompatible prior repairs, and failure outcomes.
- [ ] Repeat trials where nondeterminism exists; preserve raw receipts and all failures.
- [ ] Ensure retrieved records cannot leak held-out answers through labels, filenames, or metadata.

### Metrics

**Primary:** correct root cause **and** fully verified repair rate on held-out broken incidents.

Also report:
- False confirmations on healthy controls.
- Unsafe or unauthorized repair attempts.
- Tool calls, retrieved context size, tokens, latency, and cost.
- Memory retrieval relevance and stale/incompatible example rejection.
- Per-incident outcomes, sample size, run configuration, and variability.

Deterministic diagnostic improvements demonstrate that system's behavior, not general LLM learning. If quality stays flat but context/tool cost falls, report efficiency rather than claiming rising accuracy.

**Deliverables:** evaluation runner, frozen split manifest, raw JSON results, summary table/chart generated from those results.

**Exit gate:** a fresh run reproduces the reported protocol and metrics. A negative result is reported honestly; a favorable learning claim requires actual supporting measurements.

## Phase 9 — buyer validation and go-to-market

**Status:** excluded from the current implementation at the user's request. No landing page or marketing deliverables will be built.

**Depends on:** initial pitch; starts alongside technical work.

Tasks:
- [ ] Interview prospective data/platform engineers about recent semantic failures, current tools, time lost, and approval/security constraints.
- [ ] Record consented/anonymized notes and separate quotes from interpretation.
- [ ] Validate whether verified-memory reuse is valuable beyond standard observability alerts.
- [ ] Compare the workflow against existing catalog, observability, and incident tools.
- [ ] Define a narrow initial customer and a realistic pilot offer.
- [ ] Draft pricing as a hypothesis; do not claim revenue or willingness to pay without evidence.
- [ ] Prepare a landing page with one problem, one workflow, one measured result if available, and a pilot/contact action.
- [ ] Prepare launch/social material; publish only with explicit authorization.

**Deliverables:** interview findings, positioning brief, pilot proposal, landing page copy.

**Exit gate:** pitch distinguishes validated observations from assumptions and explains a customer benefit beyond “uses HydraDB.”

## Phase 10 — deployment, demo, and submission

**Depends on:** Phases 1–9; evaluation and commercial findings can be negative but must be documented.

Tasks:
- [ ] Provide reproducible dependency installation and pinned engine version.
- [ ] Deploy API/UI with HTTPS and persistent HydraDB storage.
- [ ] Keep engine query/admin ports private; expose only the necessary app surface.
- [ ] Protect any public mutation/reset endpoints with authentication, rate limits, and narrow origin policy.
- [ ] Use synthetic data only; exclude secrets, local environments, and runtime artifacts from source control.
- [ ] Verify restart recovery and demo reset without destroying training memory unintentionally.
- [ ] Run all unit, integration, invariant, frontend, and end-to-end checks.
- [ ] Run a fresh evaluation and inspect chart inputs against raw artifacts.
- [ ] Prepare public source repository and minimal setup/run instructions.
- [ ] Record walkthrough: incident -> context graph -> evidence -> approval -> verified repair -> memory -> new incident -> measured comparison.
- [ ] Include limitations, synthetic-data disclosure, actual engine use, and which parts are deterministic versus LLM-driven.
- [ ] Confirm official deadline, track, deliverable format, and any disclosure requirements.

**Deliverables:** live demo, public repository, walkthrough, result receipts, submission copy, deployment/runbook.

**Exit gate:** a new operator can start the documented stack and reproduce the core flow; the submitted demo does not depend on hidden credentials, mocked verification, or manual database edits.

## 6. Critical path and scheduling

```text
P0 -> P1 + P2 -> P3 -> P4 -> P5 -> P6 -> P8 -> P10
                         \-----------> P7 ------/
P9 runs alongside all implementation phases.
```

No reliable completion estimate is established yet. Time-box a live engine smoke test first; runtime incompatibility changes the rest of the schedule.

If time is short, cut in this order:
1. Animation, complex graph interactions, and visual extras.
2. Remote repair publication and additional connectors (already out of scope).
3. Extra incident archetypes beyond one with honest held-out variants and a healthy control.
4. Optional LLM orchestration, if a clearly labeled deterministic context-layer demo satisfies the track.

Never cut evidence validation, approval binding, isolated execution, invariant verification, failure disclosure, or evaluation leakage controls. Do not claim the secondary learning track if it is not demonstrated.

## 7. Risk register

| Risk | Mitigation / decision gate |
| --- | --- |
| HydraDB runtime or dialect incompatibility | Prove exact queries early; pin version; avoid Neo4j assumptions |
| Partial ingestion/writeback | Idempotent IDs and edges; incomplete records excluded from successful memory |
| Memory suggests a wrong/stale fix | Version filtering, current evidence, operator approval, full verification |
| Benchmark leakage | Frozen training snapshots, isolated scopes, hidden answer labels |
| One fixture makes “learning” trivial | Held-out variants, distractors, flat-memory comparison, honest limits |
| Candidate changes the wrong data | Temporary workspace, allowlisted transforms, conservation/non-regression checks |
| Public demo permits destructive operations | Synthetic fixture, authenticated mutations, private engine ports |
| Source review is mistaken for independent provenance | Track what was reviewed and implement afresh; no clean-room claim |
| Visual polish crowds out proof or customer work | Parallel buyer validation and early end-to-end/evaluation gates |
| Engine self-host requirement confused with hosted MCP | Verify self-hosted runtime directly; hosted OAuth is not a dependency |

## 8. Release definition of done

- [ ] Fresh installation and engine startup documented and tested.
- [ ] HydraDB is load-bearing for context retrieval and verified memory.
- [ ] Broken and healthy scenarios produce correct, evidence-backed outcomes.
- [ ] No repair executes without approval of the exact candidate.
- [ ] Verification uses executed checks, not model assertions.
- [ ] Failed/unverified repairs cannot be retrieved as successful examples.
- [ ] UI reflects live state and clearly labels previews/synthetic data.
- [ ] Evaluation includes all failures and prevents held-out leakage.
- [ ] Learning/efficiency claims match recorded measurements.
- [ ] Buyer findings and assumptions are separated.
- [ ] Secrets excluded; deployment and destructive controls reviewed.
- [ ] Live app, source, walkthrough, and limitations are ready.

## 9. Immediate next actions

1. Phase 4: implement typed incidents, deterministic diagnostic tools, and evidence-gated investigation.
2. Phase 5: bind approval to candidate hash and execute/verify in isolated workspaces.
3. Phase 6: persist/retrieve only verified repair memory.
4. Complete the command-line investigation -> approval -> verification -> memory flow before UI polish.
5. Phase 0 full reference-source review remains incomplete; do not claim otherwise.
