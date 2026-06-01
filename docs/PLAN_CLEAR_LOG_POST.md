# Plan: Change /clear-log from GET to POST

**Card:** Change /clear-log from GET to POST (Trello #69d2c2fb)
**Branch:** `feat-change-clear-log-from-get-to-post`

## Context

The `/clear-log` endpoint is a destructive operation (wipes the event log) but is exposed as a GET endpoint. HTTP spec (RFC 7231) reserves GET for safe, idempotent operations. Browser prefetches, link scanners, or crawlers could accidentally trigger log deletion.

Surfaced during peer review of card 69c98d0b (Auth-gate /get-log and /clear-log endpoints).

### Constraint: websockets 12.0 GET-only

> **Superseded (websockets 16.0 upgrade):** the server now runs on the modern `websockets.asyncio` API. The GET-only limitation still exists in v16 (`http11.Request.parse()` rejects non-GET before `process_request` runs), but it is now worked around by the module-level `_parse_request_allowing_post` shim in `mud_server.py` rather than the `_GameServerProtocol` subclass described below. The POST-only `/clear-log` behaviour is unchanged; the rest of this doc is kept as a historical record of the original implementation.

websockets 12.0 (pinned — v16+ breaks `process_request` API) rejects all non-GET HTTP methods at the wire level. `websockets.legacy.http.read_request()` raises `ValueError("unsupported HTTP method: POST")` before `process_request()` is ever called. A POST today returns 400 Bad Request silently.

## Approach

### 1. `mud_server.py` — Custom protocol subclass

**Add `_GameServerProtocol`** subclass of `WebSocketServerProtocol`:

- Override `read_http_request()` to accept both GET and POST (not just GET).
- Store the HTTP method as `self._http_method` (string: `"GET"` or `"POST"`).
- Override `process_request()` as a method (instead of a standalone function passed via callback). This gives access to `self._http_method`.
- The parent's `handshake()` calls `self.process_request(path, request_headers)` at line 522 — when defined as a method, it takes priority over the `_process_request` callback.

**Update `/clear-log` handler** inside `process_request()`:

- If method is POST: proceed with auth check + log clear (existing behavior).
- If method is GET (or anything else): return `405 Method Not Allowed` with `Allow: POST` header.

**Update both `websockets.serve()` calls** (port 8080 and TLS 8443):

- Remove `process_request=process_request` parameter.
- Add `create_protocol=_GameServerProtocol` parameter.

### 2. `tools/download_log.py` — Send POST

**Line 58:** Change `urllib.request.Request(url, headers=...)` to include `data=b""` which causes urllib to send POST. Also add a `405` error handler.

## Edge Cases

1. **Existing GET endpoints must keep working** — `/get-log`, `/admin/library-stats`, static files, and `/ws` (WebSocket upgrade) must all continue functioning identically. The subclass only restricts `/clear-log` to POST.

2. **WebSocket handshake must not break** — The WebSocket upgrade is always a GET request. Our override accepts GET, so the handshake path (`/ws`) works as before.

3. **TLS server must use same subclass** — Both the HTTP (8080) and TLS (8443) servers must use `_GameServerProtocol`.

4. **405 response format** — Must include `Allow: POST` header per RFC 7231 §6.5.5. Body should be a human-readable message.

5. **Auth check ordering** — The 405 check happens *before* the auth check. No point asking for credentials if the method is wrong. (Also avoids leaking that the endpoint exists to GET scanners, though auth-gated either way.)

6. **download_log.py error handling** — Add handling for 405 in case someone runs the old client against the new server, with a helpful message.

## Verification

- Start server, confirm `GET /clear-log` returns 405 with `Allow: POST` header.
- Confirm `POST /clear-log` with valid auth clears the log (200).
- Confirm `POST /clear-log` without auth returns 401.
- Confirm `GET /get-log` still works.
- Confirm static files still serve.
- Confirm WebSocket connections still work.
- Run `python tools/download_log.py http://localhost:8080` end-to-end.
