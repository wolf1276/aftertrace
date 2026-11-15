# Phase 1 review — HydraDB client against runtime requirements

Scope: the current `hydra.py`, `app/config.py::connect`, and the transport tests.
No client changes were made; findings are reported to the parent. The review was
re-done after the parent added the UUID query-ID fix and the expanded transport
tests.

## Meets the Phase 1 transport safety baseline

- Endpoint validation rejects non-HTTP(S) URLs, embedded credentials, query
  strings, fragments, and remote plaintext; timeout must be positive
  (`hydra.py:40-52`).
- Token and namespace header values reject CRLF injection (`hydra.py:47-50`).
- Token, graph, cell, and namespace are required at construction
  (`hydra.py:47-48`).
- Redirects are disabled so a bearer token is never forwarded to another
  endpoint (`hydra.py:14-20`).
- HTTP failures, connection failures, timeouts, and invalid JSON are converted
  to sanitized `HydraError` messages without raw bodies or credentials
  (`hydra.py:77-87`).
- Non-object envelopes, missing/duplicate/changed columns, row-width mismatches,
  and malformed typed cells are rejected (`hydra.py:88-102`, `hydra.py:23-35`).
- There are no automatic retries, so a consuming pagination cursor is never
  replayed; a failed page raises instead of returning partial rows
  (`hydra.py:71-85`).
- Pagination resends the original query, parameters, and `page_size`, plus
  `cursor` and the server's `query_id`, and holds columns stable
  (`hydra.py:94-99`, `hydra.py:108-114`).
- Each new query gets a unique `aftertrace-<uuid>` query ID, while pagination
  preserves the server-issued ID (`hydra.py:63-66`, `hydra.py:114`). The
  regression test `test_new_queries_get_unique_ids` covers this.
- The singular `bookmark` field provides read-your-writes for later queries, and
  `X-Graph-Namespace` is sent explicitly (`hydra.py:56`, `hydra.py:67-68`,
  `hydra.py:104-110`, `hydra.py:74`).
- Values are sent as parameters with an explicit `cell_id`; empty mutation rows
  are accepted as success (`hydra.py:64-66`, `hydra.py:92-103`).
- `connect()` fails explicitly when `HYDRA_TOKEN` is absent; there is no mock
  fallback (`app/config.py:15-20`).

No authentication bypass, token logging, redirect leak, or destructive-write
defect was found.

## Remaining defects and observations

### 1. P2 — Server error code/message is still discarded

`HTTPError` handling keeps only the HTTP status (`hydra.py:80-83`), and a JSON
`error` envelope raises the generic message `HydraDB rejected the query`
(`hydra.py:90-91`). Because `urlopen` raises before `json.load` for non-2xx
responses, the server's `error.code` never reaches the caller. Callers therefore
cannot distinguish `invalid_request`, `unauthenticated`, `resource_exhausted`,
and `internal` beyond the status class. Consider reading a bounded error body,
extracting only an allowlisted `code` and a length-limited message, and raising
that sanitized detail. Do not include raw bodies.

### 2. P3 — Unknown typed cells silently pass through

`decode` returns the raw `value` for every type other than `null` and `list`
(`hydra.py:35`). A `path` cell uses a different encoding and would be returned as
an untagged nested object; any future unsupported type is likewise accepted.
That is a misdecode risk rather than a current Phase 1 failure, since the
required `null`, `list`, and `vertex_id` cases are correct. Whitelist the
supported scalar types, handle `path` deliberately, or reject unknown types.

### 3. P3 — Bookmark behavior is implicit client state

`self.bookmark` is applied to every later query and is only replaced after a
complete scan (`hydra.py:56`, `hydra.py:67-68`, `hydra.py:104-110`). This gives
read-your-writes, and leaving the prior bookmark after a failed scan is safe,
but there is no per-query override or explicit clear. Document the behavior or
expose it when the application needs a different consistency point.

### 4. P3 — Minor gaps

- No test covers a `path` or unknown cell type, a non-string `bookmark`, or a
  redirect end-to-end; the redirect handler is unit-tested directly.
- Token length is not validated client-side. The server returns `401`, which is
  an acceptable explicit failure.
- `except (ValueError, UnicodeError)` is redundant because `UnicodeError` is a
  `ValueError` subclass (`hydra.py:86-87`); harmless.

## Verification performed

- `python -m unittest discover -s tests -v` from `aftertrace/`: 17 tests
  collected, 15 passed, and the two live tests skipped without
  `AFTERTRACE_LIVE_TEST=1`.
- `scripts/runtime_smoke.py`: passed all six checks against the live stack.
- Persistence write/read/cleanup modes: passed without a container restart, so
  this review does not claim restart survival.
- The head agent's acceptance receipt reports the live integration tests and a
  persistence marker surviving an actual `docker compose restart hydradb`; see
  `docs/phase1-acceptance.md`.

## Runtime impact

The client now covers the Phase 1 happy path and most failure paths. The
remaining issues are diagnostics, explicit handling of non-required cell types,
and bookmark semantics — not authentication, secret leakage, retry safety, or
partial-result behavior.
