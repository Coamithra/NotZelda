"""NPC quest handler registry and quest-aware NPC interactions."""

from server.net import send_to, broadcast_to_room

NPC_HANDLERS = {}  # (npc_name, room_id) -> async handler(player, guard)


def npc_handler(name: str, room: str):
    """Decorator to register a quest-aware NPC handler."""
    def decorator(fn):
        NPC_HANDLERS[(name, room)] = fn
        return fn
    return decorator


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
        dialog = "It's dangerous to go alone \u2014 take this!"
        player.grant_flag("has_sword")
        player.set_quest("amara", 2)
        await broadcast_to_room(player.room, {
            "type": "chat", "from": guard["name"], "text": dialog,
        })
        await send_to(player, {"type": "sword_obtained"})
        await broadcast_to_room(player.room, {
            "type": "sword_effect", "name": player.name,
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


async def handle_quest_npc(player, guard):
    """Dispatch to registered NPC handler, or fall back to static dialog."""
    handler = NPC_HANDLERS.get((guard["name"], player.room))
    if handler:
        await handler(player, guard)
    elif guard["dialog"]:
        await broadcast_to_room(player.room, {
            "type": "chat", "from": guard["name"], "text": guard["dialog"],
        })
