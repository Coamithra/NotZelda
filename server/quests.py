"""NPC quest handler registry, quest event system, and quest definitions.

NPC proximity handlers: walk-into-NPC interactions (async, run via ensure_future).
Quest events: generic game events (monster_killed, room_enter) that quest logic
reacts to. Emitters stay generic — all one-off quest logic lives here.
"""

from collections import defaultdict

from server.state import game
from server.net import send_to, broadcast_to_room

# ---------------------------------------------------------------------------
# NPC proximity handler registry (unchanged — async handlers for walk-into)
# ---------------------------------------------------------------------------

NPC_HANDLERS = {}  # (npc_name, room_id) -> async handler(player, guard)


def npc_handler(name: str, room: str):
    """Decorator to register a quest-aware NPC handler."""
    def decorator(fn):
        NPC_HANDLERS[(name, room)] = fn
        return fn
    return decorator


# ---------------------------------------------------------------------------
# Quest event system — synchronous, called from tick code
# ---------------------------------------------------------------------------

# event_type -> list of (quest_id, filter_fn, handler_fn)
_EVENT_HANDLERS: dict[str, list] = defaultdict(list)


def on_event(event_type: str, quest_id: str, **filters):
    """Decorator to register a quest event handler with optional kwarg filters.

    Example::

        @on_event("monster_killed", "clearing_guard", kind="slime", room="clearing")
        def _on_slime_killed(player, msgs, **kw):
            player.grant_flag("clearing_slime_killed")
    """
    def decorator(fn):
        if filters:
            frozen = dict(filters)
            def filter_fn(_player, **kwargs):
                return all(kwargs.get(k) == v for k, v in frozen.items())
        else:
            filter_fn = None
        _EVENT_HANDLERS[event_type].append((quest_id, filter_fn, fn))
        return fn
    return decorator


def quest_event(event_type: str, player, msgs: list, **kwargs):
    """Emit a quest event. Called synchronously during tick processing.

    All registered handlers whose filters match are called in registration order.
    Handlers can mutate player state and append to ``msgs``.
    """
    for _quest_id, filter_fn, handler_fn in _EVENT_HANDLERS.get(event_type, []):
        if filter_fn is None or filter_fn(player, **kwargs):
            handler_fn(player, msgs, **kwargs)


# ---------------------------------------------------------------------------
# Amara questline — NPC proximity handlers
# ---------------------------------------------------------------------------

@npc_handler("Amara", "chapel_sanctum")
async def amara_interact(player, guard):
    if player.quest("amara") == 0:
        player.set_quest("amara", 1)
        await broadcast_to_room(player.room, {
            "type": "chat",
            "from": player.name,
            "text": "Who could have done this to her?",
        })
        await send_to(player, {"type": "quest_update", "quest": "amara", "stage": 1})
    # Amara never speaks


@npc_handler("Priest", "old_chapel")
async def priest_interact(player, guard):
    stage = player.quest("amara")
    if stage == 0:
        dialog = "Peace be with you, traveler."
    elif stage == 1:
        dialog = "The princess has been cursed. Please, speak to the smith before you go."
    else:
        dialog = "May the light guide you. Save Princess Amara!"
    await broadcast_to_room(player.room, {
        "type": "chat", "from": guard["name"], "text": dialog,
    })


@npc_handler("Smith", "blacksmith")
async def smith_interact(player, guard):
    stage = player.quest("amara")
    if stage == 0:
        dialog = "Well met!"
    elif stage == 1:
        if player.has_flag("has_sword"):
            # Player already got sword through dialog — just advance quest
            dialog = "I see you already carry a fine blade. Good, you'll need it!"
            player.set_quest("amara", 2)
        else:
            dialog = "It's dangerous to go alone \u2014 take this!"
            player.grant_flag("has_sword")
            player.set_quest("amara", 2)
            await broadcast_to_room(player.room, {
                "type": "chat", "from": guard["name"], "text": dialog,
            })
            await send_to(player, {"type": "item_obtained", "item_type": "sword", "item_name": "Sword"})
            await broadcast_to_room(player.room, {
                "type": "item_effect", "item_type": "sword", "name": player.name,
            }, exclude=player.ws)
            return
    else:
        dialog = "Give those monsters what they deserve!"
    await broadcast_to_room(player.room, {
        "type": "chat", "from": guard["name"], "text": dialog,
    })


@npc_handler("Barmaid", "tavern")
async def barmaid_interact(player, guard):
    if player.hp < player.max_hp:
        player.hp = player.max_hp
        await send_to(player, {"type": "hp_update", "hp": player.hp, "max_hp": player.max_hp})
        dialog = "Here, let me patch you up!"
    else:
        dialog = "You look healthy to me!"
    await broadcast_to_room(player.room, {
        "type": "chat", "from": guard["name"], "text": dialog,
    })


# ---------------------------------------------------------------------------
# Clearing guard quest — event-driven
#
# Stages: 0 = never visited clearing
#         1 = visited clearing (no sword)
#         2 = has sword
#         3 = killed the slime in the clearing
# ---------------------------------------------------------------------------

@on_event("room_enter", "clearing_guard", room="clearing")
def _clearing_entered(player, msgs, **kw):
    stage = player.quest("clearing_guard")
    if stage == 0:
        player.set_quest("clearing_guard", 1)
        stage = 1
    # Upgrade to stage 2 if they got a sword since last visit
    if stage < 2 and player.has_flag("has_sword"):
        player.set_quest("clearing_guard", 2)
        # Dialog changed — let the guard speak again when approached
        from server.npc_chat import reset_npc_greeting_for_player
        reset_npc_greeting_for_player(player, "Guard", "clearing")


@on_event("monster_killed", "clearing_guard", kind="slime", room="clearing")
def _clearing_slime_killed(player, msgs, **kw):
    player.grant_flag("clearing_slime_killed")
    player.set_quest("clearing_guard", 3)
    # Dialog changed — let the guard speak again when approached
    from server.npc_chat import reset_npc_greeting_for_player
    reset_npc_greeting_for_player(player, "Guard", "clearing")


# Clearing guard — dynamic greeting via override (not @npc_handler).
# Evaluated each time the NPC is approached, so slime respawn is handled.
def _clearing_guard_greeting(player, guard):
    has_sword = player.has_flag("has_sword")
    killed_slime = player.has_flag("clearing_slime_killed")
    slime_alive = any(m.kind == "slime" and m.alive
                      for m in game.room_monsters.get("clearing", []))

    if killed_slime and not slime_alive:
        return "You're the one who slew that slime! The clearing is much safer now."
    if killed_slime and slime_alive:
        return "Another slime?! At least you've done it before — get that thing!"
    if not has_sword:
        return "You can't go out there unarmed! Visit the Smith in town square."
    if slime_alive:
        return "Careful, there's a slime lurking below! Watch yourself."
    return "Someone took care of that slime. The clearing feels safer today."


from server.npc_chat import set_npc_greeting
set_npc_greeting("Guard", "clearing", _clearing_guard_greeting)


# ---------------------------------------------------------------------------
# NPC proximity dispatch
# ---------------------------------------------------------------------------

async def handle_quest_npc(player, guard):
    """Dispatch to registered NPC handler, or fall back to greeting override / static dialog."""
    from server.npc_chat import get_npc_greeting, _last_proximity_dialog

    handler = NPC_HANDLERS.get((guard["name"], player.room))
    if handler:
        await handler(player, guard)
        return

    # Check for a dynamic greeting override (registered by quest system)
    override = get_npc_greeting(guard["name"], player.room, player, guard)
    dialog = override or guard.get("dialog", "")
    if dialog:
        _last_proximity_dialog[(player.name, guard["name"])] = dialog
        await broadcast_to_room(player.room, {
            "type": "chat", "from": guard["name"], "text": dialog,
        })
