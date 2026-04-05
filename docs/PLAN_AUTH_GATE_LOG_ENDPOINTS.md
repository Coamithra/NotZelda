# Plan: Auth-gate /get-log and /clear-log endpoints

**Card:** Auth-gate /get-log and /clear-log endpoints (Trello #69c98d0b)
**Branch:** `feat-auth-gate-get-log-and-clear-log-endpoints`

## Context

The `/get-log` and `/clear-log` HTTP endpoints in `mud_server.py` have no access control.
In production, anyone who knows the URL can read the full server event log (player names,
chat messages, join/leave timestamps) or wipe it entirely. This is a security/privacy gap.

The `/admin/library-stats` endpoint already implements `ADMIN_PASSWORD` Basic Auth.
We replicate that pattern to the log endpoints.

## Approach

### 1. `mud_server.py` — Extract auth helper, gate log endpoints

**Extract `_check_admin_auth(request_headers)`** (new helper function):
- Reads `ADMIN_PASSWORD` from env
- If unset/empty → returns 404 response (endpoint hidden)
- Validates `Authorization: Basic <b64>` header
- Decodes and checks against `admin:{password}`
- Returns `None` if auth passes, or HTTP error response tuple if it fails

**Update `/get-log` handler** (L419-421):
- Call `_check_admin_auth()` first; return error if auth fails
- Existing body logic unchanged

**Update `/clear-log` handler** (L422-424):
- Call `_check_admin_auth()` first; return error if auth fails
- Existing body logic unchanged

**Refactor `/admin/library-stats` handler** (L425-442):
- Replace inline auth block with `_check_admin_auth()` call
- Eliminates code duplication

### 2. `tools/download_log.py` — Add Basic Auth headers

- Read `ADMIN_PASSWORD` from `os.environ` (required in production)
- Build `Authorization: Basic <b64("admin:{pw}")>` header
- Use `urllib.request.Request` objects instead of bare URL strings
- If `ADMIN_PASSWORD` is not set, skip auth headers (local dev with no password = endpoints return 404, same as library-stats)
- Print a helpful message if a 401 is received

### 3. `docs/ARCHITECTURE.md` — Update docs

- Update line 59 (`tools/download_log.py` description) to mention auth requirement
- Update line 85 (event_log description) to mention auth gating

## Edge Cases

| Scenario | Expected Behavior |
|----------|-------------------|
| `ADMIN_PASSWORD` not set | All three admin endpoints return 404 (hidden) |
| No `Authorization` header | 401 with `WWW-Authenticate: Basic realm="Admin"` |
| Wrong password | 401 |
| Correct password | Normal response (log content / "Log cleared." / JSON stats) |
| Malformed base64 | 401 (existing exception handling) |
| `download_log.py` without env var | Fails with clear error or works against passwordless local dev |

## Preserved Behavior

- Authenticated access to `/get-log` returns identical plain text response
- Authenticated access to `/clear-log` returns identical "Log cleared." response
- `/admin/library-stats` behavior completely unchanged
- WebSocket `/ws` path unaffected
- Static file serving unaffected
