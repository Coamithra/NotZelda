# Plan: Stage 9 — Content Stats Endpoint

## Context

The game has an AI content generation system that manages libraries of rooms,
monsters, and tiles per dungeon type. There's a standalone content viewer
(`tools/content_viewer.py`) for browsing/editing content on port 8081, but no
way to quickly check library health and API usage from the main game server.

This card adds a lightweight read-only JSON endpoint at `/admin/library-stats`
on the game server. It answers: "How full are the libraries? How much API
budget has been used? Are there deprecated items pending cleanup?"

The user's Trello comment also asked for access safeguards — we gate the
endpoint behind `DEBUG_MODE` so it's invisible in production.

## Approach

### File: `mud_server.py`

**1. Import `ai_generator`** (for `rate_limiter` and `usage_tracker`):

```python
from server.ai_generator import rate_limiter, usage_tracker
```

This is safe — `ai_generator` only imports from `constants` and `log`,
no circular dependency risk. It's a top-level import because the endpoint
is always available in debug mode.

**2. Add handler in `process_request()`**, after the `/clear-log` block
and before the static file lookup:

```python
if path == "/admin/library-stats":
    if not DEBUG_MODE:
        return HTTPStatus.NOT_FOUND, [], b"Not Found"
    body = json.dumps(_build_library_stats(), indent=2).encode()
    return HTTPStatus.OK, [("Content-Type", "application/json")], body
```

**3. Add `_build_library_stats()` helper** that assembles the JSON payload.
Reads from three sources (all read-only):

- `game.content_libraries` — per-type library composition
- `ai_generator.rate_limiter` / `usage_tracker` — API usage
- `game.deprecated_content` — pending deprecation counts
- `game.active_dungeons` — active dungeon instance count
- `game.players` — connected player count

Response shape:

```json
{
  "server": {
    "uptime_seconds": 12345,
    "players_online": 2,
    "active_dungeons": ["d1"],
    "debug_mode": true
  },
  "libraries": {
    "d1": {
      "rooms":    { "capacity": 79, "real": 64, "permanent": 64, "custom": 0, "placeholders": 15 },
      "monsters": { "capacity": 8,  "real": 4,  "permanent": 4,  "custom": 0, "placeholders": 4 },
      "tiles":    { "capacity": 14, "real": 7,  "permanent": 7,  "custom": 0, "placeholders": 7 }
    },
    "d2": { ... }
  },
  "deprecated": {
    "d1": { "monsters": 0, "tiles": 0 },
    "d2": { "monsters": 0, "tiles": 0 }
  },
  "api_usage": {
    "backend": "cli",
    "model": "claude-haiku-4-5-20251001",
    "rate_limit": {
      "per_minute": 15,
      "per_day": 600,
      "daily_calls_used": 0
    },
    "tokens": {
      "total_input": 0,
      "total_output": 0,
      "total_cache_write": 0,
      "total_cache_read": 0,
      "total_calls": 0,
      "estimated_cost_usd": 0.0
    },
    "session": {
      "input": 0,
      "output": 0,
      "cache_write": 0,
      "cache_read": 0,
      "calls": 0,
      "estimated_cost_usd": 0.0
    }
  }
}
```

### No other files changed

- No client changes (admin endpoint, not player-facing)
- No `ai_generator.py` changes (just reading existing singletons)
- No `state.py` changes (just reading existing properties)
- No prompt file changes

## Edge Cases

1. **Libraries not yet initialized** — `game.content_libraries` could be
   empty if the endpoint is hit during startup. The helper handles this
   gracefully by iterating over whatever's there (empty dict → empty response).

2. **`process_request` is called per HTTP request** — must be fast. All data
   is in-memory property access, no disk I/O. `json.dumps` on a small dict
   is negligible.

3. **Concurrent access** — `process_request` is async but the game state is
   single-threaded (asyncio event loop). No locking needed.

4. **Production safety** — endpoint returns 404 when `DEBUG_MODE` is false,
   identical to a nonexistent path. No information leak.

5. **Import of `ai_generator`** — importing at module level means the
   `ai_generator` module initializes even if AI is never used. This is
   already the case since `dungeons.py` imports from it. No new side effects.

6. **Existing endpoints unaffected** — the new `if` block is inserted between
   `/clear-log` and the static file lookup. No change to existing behavior.

7. **`test_api_leak.py` consideration** — we're importing from `ai_generator`
   but NOT modifying it. The test checks that the API key doesn't leak into
   CLI subprocess calls. Our change is read-only access to singletons, so no
   risk — but we'll run the test anyway to be safe.
