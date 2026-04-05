# Plan: Boss Kill Messages

## Context

Boss defeats currently get the same generic "You defeated the X!" message as regular
monsters. The client already differentiates boss kills *visually* (screen flash, stronger
shake via `bossDeathEffect`), but the text messaging is identical. This card adds
differentiated wording and broadcast scope for boss kills to complete the experience.

The detection is already in place — `is_boss` is computed at `commands.py:794` from
`monster.is_boss and dinst is not None`. The existing boss-death block (lines 852-869)
handles music silencing, choir stop, and seal fragment spawning. We just need to add
dramatic messaging to this same block.

## Approach

### 1. Server: Dramatic boss kill messages (`server/commands.py`)

**Current code (lines 820-827):**
```python
# Kill message (chat log only, no popup)
monster_name = monster.kind.replace("_", " ").title()
msgs.append(("send", player, {
    "type": "log", "text": f"You defeated the {monster_name}!",
}))
msgs.append(("broadcast", room_id, {
    "type": "log", "text": f"{player.name} defeated the {monster_name}!",
}, player.ws))
```

**Change:** When `is_boss` is true, replace the generic messages with dramatic ones and
broadcast to the entire dungeon (not just the room):

- **To killer:** `"⚔ You vanquished the mighty {name}!"`
- **To dungeon (everyone):** `"⚔ {player} has vanquished the mighty {name}!"`
- Mark boss log messages with `"boss": true` so the client can style them differently
- Use `broadcast_to_dungeon()` (already imported) instead of room-only broadcast

**Implementation:** Add an `if is_boss:` / `else:` branch around lines 820-827, inside the
existing `if monster.hp <= 0:` block. The boss branch goes *before* the existing
boss-specific post-kill logic at line 852 so the message appears in the correct order.

### 2. Client: Boss kill CSS class (`client/client.html`)

Add a `chat-boss` CSS class:
```css
#chat-log .chat-boss { color: #f0c040; font-weight: bold; font-style: italic; }
```
Gold, bold, italic — matches the `chat-item` gold color but with bold weight to stand out.

### 3. Client: Handle boss flag in log messages (`client/net.js`)

In the `case "log"` handler (line 1210), check for `msg.boss` and use `chat-boss` class:
```javascript
case "log": {
  const cls = msg.boss ? "chat-boss" : "chat-system";
  appendChatLog(`<span class="${cls}">${escHtml(msg.text)}</span>`);
  break;
}
```

## Edge Cases

1. **Non-dungeon bosses:** `is_boss` requires `dinst is not None`, so overworld bosses
   (if they ever exist) won't trigger the dungeon broadcast. This is correct — there's no
   dungeon instance to broadcast to. They'll still get the dramatic message text though
   since we can check `monster.is_boss` directly.
   → Decision: use `monster.is_boss` for message text, `is_boss` (which includes dungeon
   check) for `broadcast_to_dungeon()`.

2. **Solo player:** `broadcast_to_dungeon()` sends to all dungeon players. If solo, the
   killer gets both their personal "send" message and the dungeon broadcast. This is fine —
   the personal message is "You vanquished..." and the broadcast is "{name} has
   vanquished..." so they're different perspectives (same pattern as current code).

3. **Player not in dungeon when boss dies (left mid-fight):** `broadcast_to_dungeon()`
   checks `p.room in instance.active_rooms`, so only current dungeon occupants get it.

4. **Multiple players in boss room:** All see the broadcast. Only the killer gets the
   personal "You vanquished..." message. Same pattern as current code.

5. **Existing boss post-kill logic preserved:** Music silencing, choir stop, seal fragment
   spawn — all remain untouched. We're only changing the log message block.

6. **Gauntlet bosses:** Gauntlet rooms use `room_id.startswith("gauntlet_")` and don't
   have a dungeon instance (`dinst` is None), so `is_boss` will be False. Gauntlet boss
   kills use regular messages. This seems correct for the gauntlet context.
