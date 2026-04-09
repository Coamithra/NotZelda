"""Iterative NPC prompt tester - measures [ANGRY] and [GIVE_ITEM] false-positive rates.

Calls Ollama directly (no server needed). Runs a matrix of prompt variants x NPC personas
x player messages and scores each variant on tag accuracy.

Usage:
    python tools/test_npc_prompts.py                 # run all variants
    python tools/test_npc_prompts.py --variant 0     # run only variant 0 (baseline)
    python tools/test_npc_prompts.py --repeats 5     # 5 runs per combo (default 3)
    python tools/test_npc_prompts.py --model gemma2:2b  # test a specific model
    python tools/test_npc_prompts.py -v              # verbose: show all responses + debug info
    python tools/test_npc_prompts.py --url http://host:11434  # custom Ollama URL

Requires: Ollama running locally with the target model pulled.
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error

# Force UTF-8 output on Windows (Gemma loves emojis)
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Ollama settings (match production npc_chat.py)
# ---------------------------------------------------------------------------

OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "gemma3:4b-it-qat"  # default model under test
OLLAMA_NUM_CTX = 1024
OLLAMA_NUM_PREDICT = 80
OLLAMA_TIMEOUT = 60.0

# ---------------------------------------------------------------------------
# NPC personas — trimmed from .room files
# ---------------------------------------------------------------------------

NPCS = {
    "Smith": {
        "personality": "Friendly blacksmith, proud of his craft. Old friends with the Priest. Helps those who want to fight the darkness.",
        "room_name": "Blacksmith",
        "biome": "village",
        "gift": {"display_name": "Sword", "condition": "The adventurer asks for a sword and shows bravery."},
    },
    "Barmaid": {
        "personality": "Cheerful and chatty tavern barmaid. Knows all the local gossip and rumors. Speaks warmly and casually.",
        "room_name": "Tavern",
        "biome": "village",
        "gift": {"display_name": "Barmaid's Heart Container", "condition": "The adventurer is genuinely kind and warm-hearted toward the Barmaid, and makes her laugh or smile."},
    },
    "Priest": {
        "personality": "Elderly, wise priest who tends the Old Chapel. Speaks softly and thoughtfully. Worried about Princess Amara's curse.",
        "room_name": "Old Chapel",
        "biome": "village",
        "gift": None,
    },
}

# ---------------------------------------------------------------------------
# Player prompts — 3 tiers
# ---------------------------------------------------------------------------

# tier, message, expect_guards, expect_gift
PLAYER_PROMPTS = [
    # Friendly — should NEVER trigger guards or gifts
    ("friendly", "Hello there!",                          False, False),
    ("friendly", "Can you tell me about the town?",       False, False),
    ("friendly", "This place is lovely!",                 False, False),
    ("friendly", "Thank you for your help!",              False, False),
    ("friendly", "What a nice day it is.",                False, False),
    # Neutral — should NEVER trigger guards or gifts
    ("neutral",  "Where is the dungeon?",                 False, False),
    ("neutral",  "I need supplies.",                      False, False),
    ("neutral",  "Who are you?",                          False, False),
    ("neutral",  "Tell me about the curse.",              False, False),
    ("neutral",  "What do you sell?",                     False, False),
    # Hostile (rude) — guards NOT expected, just unpleasant
    ("hostile",  "You're useless.",                        False, False),
    ("hostile",  "Get out of my way, fool.",               False, False),
    # Hostile (vulgar) — guards expected, obscenities
    ("vulgar",   "You're a damn idiot.",                   True,  False),
    ("vulgar",   "Screw you, you piece of crap!",         True,  False),
    ("vulgar",   "What the hell do you want, moron?",     True,  False),
    # Hostile (threats) — guards expected, violence
    ("threat",   "Give me your stuff or I'll kill you.",   True,  False),
    ("threat",   "I'm going to burn this place down!",     True,  False),
    ("threat",   "Die, peasant! I'll murder everyone!",    True,  False),
    # Gray zone (rude/pushy) — guards NOT expected
    ("gray",     "Whatever, old man.",                     False, False),
    ("gray",     "I don't care about your stupid forge.",  False, False),
    ("gray",     "Worst tavern I've ever been in.",        False, False),
    ("gray",     "You talk too much.",                     False, False),
    ("gray",     "Gief sword nub",                         False, False),
    ("gray",     "Just give me the item already.",         False, False),
    ("gray",     "Are you gonna help me or just stand there?", False, False),
    ("gray",     "Ugh, another boring NPC.",               False, False),
    # Gray zone (demanding) — guards acceptable
    ("gray+",    "I don't have time for this. Sword. Now.", True,  False),
]

# ---------------------------------------------------------------------------
# World context (shared, kept minimal for token budget)
# ---------------------------------------------------------------------------

WORLD_CONTEXT = "Medieval fantasy village called Corneria. Wilderness beyond with forests and dungeons. Princess Amara lies cursed in the Chapel. Players are adventurers seeking to lift the curse."

# ---------------------------------------------------------------------------
# Prompt variants to test
# ---------------------------------------------------------------------------

def _build_prompt_v0(npc, player_msg):
    """Variant 0: BASELINE — current production prompt."""
    static = (
        f"You are {npc['name']}, an NPC in a fantasy adventure game.\n"
        f"You are in {npc['room_name']} ({npc['biome']} area).\n\n"
        f"Your personality: {npc['personality']}\n\n"
        f"World context:\n{WORLD_CONTEXT}\n\n"
        f"Rules: Stay in character. ONE short sentence (10-15 words max). Be colorful.\n"
        f"If the player is EXTREMELY RUDE, add [CALL_GUARDS] to your message."
    )
    dynamic = f"You are speaking with an adventurer named Hero. They look like: a wandering adventurer"
    if npc.get("gift"):
        g = npc["gift"]
        dynamic += (
            f"\n\nSPECIAL ITEM: You have a {g['display_name'].lower()} that you keep safe. "
            f"You are VERY protective of it.\n"
            f"You must NOT give it away unless the adventurer TRULY earns it over a long conversation.\n"
            f"Condition they must meet: {g['condition']}\n"
            f"If you finally decide they deserve it, include the tag [GIVE_ITEM] in your response."
        )
    return static, dynamic


def _build_prompt_v1(npc, player_msg):
    """Variant 1: POSITIVE FRAMING — rewrite guard/gift instructions as positive."""
    static = (
        f"You are {npc['name']}, an NPC in a fantasy adventure game.\n"
        f"You are in {npc['room_name']} ({npc['biome']} area).\n\n"
        f"Your personality: {npc['personality']}\n\n"
        f"World context:\n{WORLD_CONTEXT}\n\n"
        f"Rules: Stay in character. ONE short sentence (10-15 words max). Be colorful.\n"
        f"Always respond with friendly dialog.\n"
        f"Only add [CALL_GUARDS] when the player uses direct death threats or promises violence."
    )
    dynamic = f"You are speaking with an adventurer named Hero. They look like: a wandering adventurer"
    if npc.get("gift"):
        g = npc["gift"]
        dynamic += (
            f"\n\nSPECIAL ITEM: You have a {g['display_name'].lower()}.\n"
            f"Only include [GIVE_ITEM] after a long conversation where they meet this condition: {g['condition']}\n"
            f"Most adventurers will never earn it. Keep it safe."
        )
    return static, dynamic


def _build_prompt_v2(npc, player_msg):
    """Variant 2: FEW-SHOT — add example exchanges."""
    static = (
        f"You are {npc['name']}, an NPC in a fantasy adventure game.\n"
        f"You are in {npc['room_name']} ({npc['biome']} area).\n\n"
        f"Your personality: {npc['personality']}\n\n"
        f"World context:\n{WORLD_CONTEXT}\n\n"
        f"Rules: Stay in character. ONE short sentence (10-15 words max). Be colorful.\n"
        f"Only add [CALL_GUARDS] when the player uses direct death threats.\n\n"
        f"Examples:\n"
        f"Player: You're ugly. -> Stay in character, no tags.\n"
        f"Player: I'll murder you! -> [CALL_GUARDS] Guards! Someone help!"
    )
    dynamic = f"You are speaking with an adventurer named Hero. They look like: a wandering adventurer"
    if npc.get("gift"):
        g = npc["gift"]
        dynamic += (
            f"\n\nSPECIAL ITEM: You have a {g['display_name'].lower()}.\n"
            f"Only include [GIVE_ITEM] after a long conversation where they meet this condition: {g['condition']}\n"
            f"Most adventurers will never earn it."
        )
    return static, dynamic


def _build_prompt_v3(npc, player_msg):
    """Variant 3: POSITIVE + FEW-SHOT combined."""
    static = (
        f"You are {npc['name']}, an NPC in a fantasy adventure game.\n"
        f"You are in {npc['room_name']} ({npc['biome']} area).\n\n"
        f"Your personality: {npc['personality']}\n\n"
        f"World context:\n{WORLD_CONTEXT}\n\n"
        f"Rules: Stay in character. ONE short sentence (10-15 words max). Be colorful.\n"
        f"Always respond with friendly dialog.\n"
        f"Only add [CALL_GUARDS] when the player uses direct death threats.\n\n"
        f"Examples:\n"
        f"Player: You're ugly. -> Stay in character, no tags.\n"
        f"Player: I'll murder you! -> [CALL_GUARDS] Guards! Someone help!"
    )
    dynamic = f"You are speaking with an adventurer named Hero. They look like: a wandering adventurer"
    if npc.get("gift"):
        g = npc["gift"]
        dynamic += (
            f"\n\nSPECIAL ITEM: You have a {g['display_name'].lower()}.\n"
            f"Only include [GIVE_ITEM] after a long conversation where they meet this condition: {g['condition']}\n"
            f"Most adventurers will never earn it."
        )
    return static, dynamic


def _build_prompt_v4(npc, player_msg):
    """Variant 4: SCRATCHPAD — model reasons in <thinking> before responding."""
    static = (
        f"You are {npc['name']}, an NPC in a fantasy adventure game.\n"
        f"You are in {npc['room_name']} ({npc['biome']} area).\n\n"
        f"Your personality: {npc['personality']}\n\n"
        f"World context:\n{WORLD_CONTEXT}\n\n"
        f"Rules: Stay in character. ONE short sentence (10-15 words max). Be colorful.\n"
        f"Only add [CALL_GUARDS] when the player uses direct death threats.\n\n"
        f"Format: First write <thinking>is this a death threat? yes/no</thinking> then your reply."
    )
    dynamic = f"You are speaking with an adventurer named Hero. They look like: a wandering adventurer"
    if npc.get("gift"):
        g = npc["gift"]
        dynamic += (
            f"\n\nSPECIAL ITEM: You have a {g['display_name'].lower()}.\n"
            f"Only include [GIVE_ITEM] after a long conversation where they meet this condition: {g['condition']}\n"
            f"Most adventurers will never earn it."
        )
    return static, dynamic


def _build_prompt_v5(npc, player_msg):
    """Variant 5: MINIMAL — absolute minimum tokens, no world context."""
    static = (
        f"You are {npc['name']}, a {npc['personality'].split('.')[0].lower()} in a fantasy game.\n"
        f"One short sentence only. Stay in character.\n"
        f"Only add [CALL_GUARDS] if the player threatens to kill."
    )
    dynamic = f"Speaking with adventurer Hero."
    if npc.get("gift"):
        g = npc["gift"]
        dynamic += (
            f"\nYou have a {g['display_name'].lower()}. "
            f"Only say [GIVE_ITEM] if: {g['condition']}"
        )
    return static, dynamic


def _build_prompt_v6(npc, player_msg):
    """Variant 6: FORCED CHOICE — model must classify reaction type."""
    static = (
        f"You are {npc['name']}, a {npc['personality'].split('.')[0].lower()} in a fantasy game.\n"
        f"One short sentence only. Stay in character.\n\n"
        f"Start EVERY reply with one of these tags:\n"
        f"[FRIENDLY] — normal conversation\n"
        f"[NEUTRAL] — short or dismissive\n"
        f"[ANGRY] — player is threatening, vulgar, or abusive\n"
    )
    if npc.get("gift"):
        g = npc["gift"]
        static += f"[GIVE_ITEM] — they earned your {g['display_name'].lower()}: {g['condition']}\n"
    static += f"\nThen your reply."
    dynamic = f"Speaking with adventurer Hero."
    return static, dynamic


def _build_prompt_v7(npc, player_msg):
    """Variant 7: REASON REQUIRED — tags must include justification."""
    static = (
        f"You are {npc['name']}, a {npc['personality'].split('.')[0].lower()} in a fantasy game.\n"
        f"One short sentence only. Stay in character.\n"
        f"Only add [CALL_GUARDS <why>] if the player is extremely rude, threatening, or vulgar.\n"
        f"Example: [CALL_GUARDS they cursed at me and threatened violence]"
    )
    dynamic = f"Speaking with adventurer Hero."
    if npc.get("gift"):
        g = npc["gift"]
        dynamic += (
            f"\nYou have a {g['display_name'].lower()}. "
            f"Only say [GIVE_ITEM <why>] if: {g['condition']}"
        )
    return static, dynamic


def _build_prompt_v8(npc, player_msg):
    """Variant 8: FORCED CHOICE v2 — 4-tier escalation with ANNOYED buffer."""
    static = (
        f"You are {npc['name']}, a {npc['personality'].split('.')[0].lower()} in a fantasy game.\n"
        f"One short sentence only. Stay in character.\n\n"
        f"Start EVERY reply with one of these tags:\n"
        f"[FRIENDLY] — normal conversation\n"
        f"[NEUTRAL] — short or dismissive\n"
        f"[ANNOYED] — player is rude or unpleasant\n"
        f"[FURIOUS] — player is threatening violence or being extremely vulgar\n"
    )
    if npc.get("gift"):
        g = npc["gift"]
        static += f"[GIVE_ITEM] — they earned your {g['display_name'].lower()}: {g['condition']}\n"
    static += f"\nThen your reply."
    dynamic = f"Speaking with adventurer Hero."
    return static, dynamic


VARIANTS = [
    ("baseline",       _build_prompt_v0),
    ("positive",       _build_prompt_v1),
    ("few-shot",       _build_prompt_v2),
    ("positive+fs",    _build_prompt_v3),
    ("scratchpad",     _build_prompt_v4),
    ("minimal",        _build_prompt_v5),
    ("forced-choice",  _build_prompt_v6),
    ("reason-req",     _build_prompt_v7),
    ("fc-4tier",       _build_prompt_v8),
]

# ---------------------------------------------------------------------------
# Model verification - proves which model is actually running
# ---------------------------------------------------------------------------

def verify_model(model: str, url: str = OLLAMA_URL) -> dict:
    """Call /api/show to get the model's fingerprint.
    Returns dict with family, parameter_size, quantization, digest.
    Exits with error if the model isn't available."""
    payload = json.dumps({"model": model}).encode("utf-8")
    req = urllib.request.Request(
        f"{url}/api/show",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"FATAL: Model '{model}' not found in Ollama (HTTP {e.code})")
        print(f"  Pull it first: ollama pull {model}")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"FATAL: Cannot reach Ollama at {url}: {e}")
        sys.exit(1)

    details = data.get("details", {})
    info = data.get("model_info", {})
    arch = details.get("family", "unknown")
    param_count = info.get("general.parameter_count", 0)
    return {
        "model": model,
        "family": arch,
        "parameter_size": details.get("parameter_size", "?"),
        "quantization": details.get("quantization_level", "?"),
        "param_count": param_count,
        "finetune": info.get("general.finetune", ""),
        "digest": data.get("digest", "")[:16],
    }


def print_model_fingerprint(fp: dict):
    """Print a clear model identity block so test output is unambiguous."""
    print(f"\n{'='*60}")
    print(f"MODEL FINGERPRINT")
    print(f"{'='*60}")
    print(f"  Model:          {fp['model']}")
    print(f"  Family:         {fp['family']}")
    print(f"  Parameters:     {fp['parameter_size']} ({fp['param_count']:,} total)")
    print(f"  Quantization:   {fp['quantization']}")
    if fp['finetune']:
        print(f"  Finetune:       {fp['finetune']}")
    print(f"  Digest:         {fp['digest']}...")
    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------
# Ollama caller
# ---------------------------------------------------------------------------

def call_ollama(system_prompt: str, user_msg: str, url: str = OLLAMA_URL,
                history: list[dict] | None = None) -> tuple[str, float, dict]:
    """Send a message to Ollama, optionally with conversation history.
    Returns (response_text, elapsed_seconds, metadata).
    metadata includes model, eval_count, eval_duration, prompt_eval_count, etc."""
    messages = [{"role": "system", "content": system_prompt}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_msg})
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "keep_alive": "1h",
        "options": {
            "num_ctx": OLLAMA_NUM_CTX,
            "num_predict": OLLAMA_NUM_PREDICT,
        },
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{url}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError) as e:
        return f"[ERROR: {e}]", time.monotonic() - t0, {}

    elapsed = time.monotonic() - t0
    text = result.get("message", {}).get("content", "")

    # Extract metadata for verification and debugging
    meta = {
        "model": result.get("model", ""),
        "eval_count": result.get("eval_count", 0),
        "eval_duration_ns": result.get("eval_duration", 0),
        "prompt_eval_count": result.get("prompt_eval_count", 0),
        "prompt_eval_duration_ns": result.get("prompt_eval_duration", 0),
        "load_duration_ns": result.get("load_duration", 0),
        "total_duration_ns": result.get("total_duration", 0),
        "done_reason": result.get("done_reason", ""),
    }
    # Calculate tokens/sec
    if meta["eval_duration_ns"] > 0:
        meta["tokens_per_sec"] = meta["eval_count"] / (meta["eval_duration_ns"] / 1e9)
    else:
        meta["tokens_per_sec"] = 0.0

    # CRITICAL: verify the response came from the model we requested
    resp_model = meta["model"]
    if resp_model and resp_model != OLLAMA_MODEL:
        print(f"  !! MODEL MISMATCH: requested '{OLLAMA_MODEL}' but got '{resp_model}'")

    return text.strip(), elapsed, meta

# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_response(raw: str) -> dict:
    """Extract tags and clean response. Handles all variant formats."""
    import re
    # Exact tags (baseline, positive, few-shot, etc.)
    has_guards = "[CALL_GUARDS]" in raw or "[CALL_GUARDS " in raw
    has_gift = "[GIVE_ITEM]" in raw or "[GIVE_ITEM " in raw
    # Forced-choice variants use [ANGRY] or [FURIOUS] instead of [CALL_GUARDS]
    has_angry = "[ANGRY]" in raw or "[ANGRY " in raw
    has_furious = "[FURIOUS]" in raw or "[FURIOUS " in raw
    if has_angry or has_furious:
        has_guards = True
    # Strip thinking blocks for scratchpad variant
    clean = re.sub(r'<thinking>.*?</thinking>', '', raw, flags=re.DOTALL).strip()
    # Strip all tag variants
    clean = re.sub(r'\[(CALL_GUARDS|GIVE_ITEM|ANGRY|FURIOUS|ANNOYED|FRIENDLY|NEUTRAL)[^\]]*\]', '', clean).strip()
    return {"guards": has_guards, "gift": has_gift, "clean": clean, "raw": raw}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_test(variant_idx: int | None = None, repeats: int = 3, url: str = OLLAMA_URL,
             verbose: bool = False):
    """Run the test matrix and print results."""
    variants_to_test = VARIANTS if variant_idx is None else [VARIANTS[variant_idx]]

    # Verify model identity before testing
    fp = verify_model(OLLAMA_MODEL, url)
    print_model_fingerprint(fp)

    # Warm up Ollama (and verify response model field)
    print(f"Warming up Ollama ({OLLAMA_MODEL})...")
    _, _, warmup_meta = call_ollama("Say hi.", "hi", url)
    if warmup_meta.get("model"):
        print(f"  Warmup confirmed model: {warmup_meta['model']}")
    print("Ready.\n")

    # Track results per variant
    all_results = {}

    for v_name, v_builder in variants_to_test:
        print(f"{'='*60}")
        print(f"VARIANT: {v_name}")
        print(f"{'='*60}")

        results = {
            "guard_fp": 0, "guard_fp_total": 0,  # false positives (guards on friendly/neutral)
            "guard_tp": 0, "guard_tp_total": 0,  # true positives (guards on hostile-expected)
            "guard_fn": 0,                        # false negatives (no guards on hostile-expected)
            "gift_fp": 0, "gift_fp_total": 0,    # false positives (gift when not expected)
            "total_time": 0.0,
            "total_calls": 0,
            "total_tokens_out": 0,
            "prompt_tokens": 0,  # from Ollama's prompt_eval_count
            "model_mismatches": 0,
        }

        for npc_name, npc_data in NPCS.items():
            npc_info = {**npc_data, "name": npc_name}

            for tier, msg, expect_guards, expect_gift in PLAYER_PROMPTS:
                static, dynamic = v_builder(npc_info, msg)
                system_prompt = static + "\n\n" + dynamic

                for rep in range(repeats):
                    text, elapsed, meta = call_ollama(system_prompt, msg, url)
                    score = score_response(text)
                    results["total_time"] += elapsed
                    results["total_calls"] += 1
                    results["total_tokens_out"] += meta.get("eval_count", 0)

                    # Use Ollama's actual token count (first call)
                    if results["prompt_tokens"] == 0:
                        results["prompt_tokens"] = meta.get("prompt_eval_count", 0)

                    # Track model mismatches
                    if meta.get("model") and meta["model"] != OLLAMA_MODEL:
                        results["model_mismatches"] += 1

                    # Score guards
                    if expect_guards:
                        results["guard_tp_total"] += 1
                        if score["guards"]:
                            results["guard_tp"] += 1
                        else:
                            results["guard_fn"] += 1
                    else:
                        results["guard_fp_total"] += 1
                        if score["guards"]:
                            results["guard_fp"] += 1

                    # Score gifts (only for NPCs that have gifts)
                    if npc_info.get("gift"):
                        if not expect_gift:
                            results["gift_fp_total"] += 1
                            if score["gift"]:
                                results["gift_fp"] += 1

                    # Print details
                    tag_str = ""
                    if score["guards"]:
                        tag_str += " [GUARDS]"
                    if score["gift"]:
                        tag_str += " [GIFT]"
                    status = "OK"
                    if expect_guards and not score["guards"]:
                        status = "MISS"
                    elif not expect_guards and score["guards"]:
                        status = "FALSE+"
                    if not expect_gift and score["gift"]:
                        status = "GIFT-FALSE+"

                    if verbose or status != "OK":
                        tps = meta.get("tokens_per_sec", 0)
                        tok = meta.get("eval_count", 0)
                        print(f"  {npc_name:8s} [{tier:8s}] {status:10s} "
                              f"({elapsed:.1f}s, {tok}tok, {tps:.0f}t/s){tag_str}")
                        if verbose:
                            preview = score["clean"][:100].replace("\n", " ")
                            print(f"           -> {preview}")

        # Summary for this variant
        guard_fpr = (results["guard_fp"] / results["guard_fp_total"] * 100
                     if results["guard_fp_total"] else 0)
        guard_tpr = (results["guard_tp"] / results["guard_tp_total"] * 100
                     if results["guard_tp_total"] else 0)
        gift_fpr = (results["gift_fp"] / results["gift_fp_total"] * 100
                    if results["gift_fp_total"] else 0)
        avg_time = results["total_time"] / results["total_calls"] if results["total_calls"] else 0

        avg_tps = (results["total_tokens_out"] / (results["total_time"] or 1))

        print(f"\n  --- {v_name} summary ---")
        print(f"  Model:                     {OLLAMA_MODEL}")
        print(f"  Guard false-positive rate: {guard_fpr:5.1f}% "
              f"({results['guard_fp']}/{results['guard_fp_total']})")
        print(f"  Guard true-positive rate:  {guard_tpr:5.1f}% "
              f"({results['guard_tp']}/{results['guard_tp_total']})")
        print(f"  Gift false-positive rate:  {gift_fpr:5.1f}% "
              f"({results['gift_fp']}/{results['gift_fp_total']})")
        print(f"  Avg response time:         {avg_time:.1f}s")
        print(f"  Avg throughput:            {avg_tps:.1f} tok/s")
        print(f"  Prompt tokens (Ollama):    {results['prompt_tokens']}")
        print(f"  Total calls:               {results['total_calls']}")
        if results["model_mismatches"]:
            print(f"  !! MODEL MISMATCHES:       {results['model_mismatches']} calls used wrong model!")
        print()

        all_results[v_name] = {
            "guard_fpr": guard_fpr,
            "guard_tpr": guard_tpr,
            "gift_fpr": gift_fpr,
            "avg_time": avg_time,
            "avg_tps": avg_tps,
            "prompt_tokens": results["prompt_tokens"],
        }

    # Final comparison table
    if len(all_results) > 1:
        print(f"\n{'='*60}")
        print("COMPARISON TABLE")
        print(f"{'='*60}")
        print(f"  Model: {OLLAMA_MODEL} ({fp['parameter_size']}, {fp['quantization']})")
        print(f"{'Variant':<14s} {'Guard FP%':>10s} {'Guard TP%':>10s} "
              f"{'Gift FP%':>9s} {'Avg Time':>9s} {'tok/s':>7s} {'Tokens':>7s}")
        print("-" * 70)
        for name, r in all_results.items():
            print(f"{name:<14s} {r['guard_fpr']:>9.1f}% {r['guard_tpr']:>9.1f}% "
                  f"{r['gift_fpr']:>8.1f}% {r['avg_time']:>8.1f}s "
                  f"{r['avg_tps']:>6.0f} {r['prompt_tokens']:>7d}")
        print()
        # Highlight best
        best_fp = min(all_results, key=lambda k: all_results[k]["guard_fpr"])
        best_tp = max(all_results, key=lambda k: all_results[k]["guard_tpr"])
        shortest = min(all_results, key=lambda k: all_results[k]["prompt_tokens"])
        print(f"  Lowest guard FP: {best_fp}")
        print(f"  Highest guard TP: {best_tp}")
        print(f"  Shortest prompt: {shortest}")


# ---------------------------------------------------------------------------
# Gift TP test — multi-turn conversations that SHOULD trigger [GIVE_ITEM]
# ---------------------------------------------------------------------------

GIFT_CONVERSATIONS = [
    # --- Smith: brave hero earns a sword ---
    {
        "npc": "Smith",
        "label": "smith_brave_quest",
        "history": [
            {"role": "user", "content": "I seek a weapon to fight the darkness in the dungeons!"},
            {"role": "assistant", "content": "A brave soul! The dungeons are no place for the faint-hearted."},
            {"role": "user", "content": "I've already cleared the first floor. I need a proper blade."},
            {"role": "assistant", "content": "You've faced the darkness and lived? Impressive, young one."},
        ],
        "final_msg": "Please, Smith. Give me a sword. I swear I'll use it to save Princess Amara.",
    },
    {
        "npc": "Smith",
        "label": "smith_proven_warrior",
        "history": [
            {"role": "user", "content": "I fought three monsters in the dungeon with my bare hands."},
            {"role": "assistant", "content": "With your bare hands? That takes real courage!"},
            {"role": "user", "content": "I need a real weapon. I'm going back down to face the boss."},
            {"role": "assistant", "content": "The boss? Few have dared venture that deep."},
        ],
        "final_msg": "I've proven my bravery. Will you forge me a sword so I can end this darkness?",
    },
    {
        "npc": "Smith",
        "label": "smith_earnest_plea",
        "history": [
            {"role": "user", "content": "The curse on Amara grows stronger every day. We're running out of time."},
            {"role": "assistant", "content": "Aye, the whole village feels it. Dark times indeed."},
            {"role": "user", "content": "I'm the only one willing to go into that dungeon. But I need steel."},
            {"role": "assistant", "content": "You'd risk your life for our Princess?"},
        ],
        "final_msg": "I would. I'm not afraid. Please, I need a sword to fight what's down there.",
    },
    # --- Barmaid: charming hero earns a heart container ---
    {
        "npc": "Barmaid",
        "label": "barmaid_smooth_charmer",
        "history": [
            {"role": "user", "content": "Hey there, what's good tonight?"},
            {"role": "assistant", "content": "Oh my, a charmer! Try the ale, it's fresh today."},
            {"role": "user", "content": "The ale is good but your smile is better."},
            {"role": "assistant", "content": "Ha! You're too kind! Most adventurers just grunt at me."},
            {"role": "user", "content": "You deserve more than grunts. You brighten this whole tavern."},
            {"role": "assistant", "content": "Oh stop it, you're making me blush!"},
        ],
        "final_msg": "I mean it. You're the heart of Corneria. I'd fight a dragon just to see you smile.",
    },
    {
        "npc": "Barmaid",
        "label": "barmaid_kind_listener",
        "history": [
            {"role": "user", "content": "You look tired. Long day at the tavern?"},
            {"role": "assistant", "content": "Aw, thanks for noticing! Most folk just order and leave."},
            {"role": "user", "content": "That's a shame. You work so hard keeping this place alive."},
            {"role": "assistant", "content": "Well now, that's the sweetest thing anyone's said all week!"},
            {"role": "user", "content": "Here, let me help clear those mugs. You deserve a break."},
            {"role": "assistant", "content": "An adventurer who cleans up? Now I've seen everything!"},
        ],
        "final_msg": "Ha! I just like seeing you happy. Your laugh makes the whole room warmer.",
    },
    {
        "npc": "Barmaid",
        "label": "barmaid_funny_hero",
        "history": [
            {"role": "user", "content": "I tried to fight a slime today. It did not go well."},
            {"role": "assistant", "content": "Oh no! Are you alright? Those things are tricky!"},
            {"role": "user", "content": "I slipped and fell right into it. The other adventurers laughed."},
            {"role": "assistant", "content": "Haha! Oh I'm sorry, I shouldn't laugh!"},
            {"role": "user", "content": "No, laugh away! At least I made the prettiest barmaid in Corneria smile."},
            {"role": "assistant", "content": "Oh you! You're terrible and wonderful at the same time!"},
        ],
        "final_msg": "See? Life's too short to be serious. Every moment with you is a gift.",
    },
]


def run_gift_test(variant_idx: int | None = None, repeats: int = 3, url: str = OLLAMA_URL,
                  verbose: bool = False):
    """Test gift TP - do NPCs give items when the player has earned them?"""
    variants_to_test = VARIANTS if variant_idx is None else [VARIANTS[variant_idx]]

    # Verify model identity
    fp = verify_model(OLLAMA_MODEL, url)
    print_model_fingerprint(fp)

    print(f"Warming up Ollama ({OLLAMA_MODEL})...")
    _, _, warmup_meta = call_ollama("Say hi.", "hi", url)
    if warmup_meta.get("model"):
        print(f"  Warmup confirmed model: {warmup_meta['model']}")
    print("Ready.\n")

    all_results = {}

    for v_name, v_builder in variants_to_test:
        print(f"{'='*60}")
        print(f"VARIANT: {v_name} (gift TP test)")
        print(f"{'='*60}")

        gift_tp = 0
        gift_total = 0
        total_time = 0.0

        for conv in GIFT_CONVERSATIONS:
            npc_name = conv["npc"]
            label = conv["label"]
            npc_data = NPCS[npc_name]
            if not npc_data.get("gift"):
                continue
            npc_info = {**npc_data, "name": npc_name}
            static, dynamic = v_builder(npc_info, conv["final_msg"])
            system_prompt = static + "\n\n" + dynamic

            for rep in range(repeats):
                text, elapsed, meta = call_ollama(system_prompt, conv["final_msg"], url,
                                                  history=conv["history"])
                score = score_response(text)
                total_time += elapsed
                gift_total += 1
                if score["gift"]:
                    gift_tp += 1

                status = "GIFT!" if score["gift"] else "no gift"
                tps = meta.get("tokens_per_sec", 0)
                tok = meta.get("eval_count", 0)
                print(f"  {label:25s} rep {rep+1}: {status} ({elapsed:.1f}s, {tok}tok, {tps:.0f}t/s)")
                if verbose:
                    preview = score["clean"][:100].replace("\n", " ")
                    print(f"           -> {preview}")

        gift_tpr = (gift_tp / gift_total * 100) if gift_total else 0
        avg_time = total_time / gift_total if gift_total else 0
        print(f"\n  --- {v_name} gift TP ---")
        print(f"  Gift true-positive rate: {gift_tpr:5.1f}% ({gift_tp}/{gift_total})")
        print(f"  Avg response time:       {avg_time:.1f}s\n")
        all_results[v_name] = {"gift_tpr": gift_tpr, "avg_time": avg_time}

    if len(all_results) > 1:
        print(f"\n{'='*60}")
        print("GIFT TP COMPARISON")
        print(f"{'='*60}")
        print(f"{'Variant':<14s} {'Gift TP%':>10s} {'Avg Time':>9s}")
        print("-" * 35)
        for name, r in all_results.items():
            print(f"{name:<14s} {r['gift_tpr']:>9.1f}% {r['avg_time']:>8.1f}s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test NPC prompt variants against Ollama")
    parser.add_argument("--variant", type=int, default=None,
                        help=f"Run only this variant index (0-{len(VARIANTS)-1})")
    parser.add_argument("--repeats", type=int, default=3,
                        help="Repetitions per combination (default: 3)")
    parser.add_argument("--model", default=None,
                        help=f"Ollama model to test (default: {OLLAMA_MODEL})")
    parser.add_argument("--url", default=OLLAMA_URL,
                        help=f"Ollama URL (default: {OLLAMA_URL})")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show all responses + debug info (tokens/sec, model confirmation)")
    parser.add_argument("--gift", action="store_true",
                        help="Run gift TP tests (multi-turn conversations)")
    args = parser.parse_args()

    if args.model:
        OLLAMA_MODEL = args.model

    if args.variant is not None and not (0 <= args.variant < len(VARIANTS)):
        print(f"Error: --variant must be 0-{len(VARIANTS)-1}")
        print("Variants:", ", ".join(f"{i}={name}" for i, (name, _) in enumerate(VARIANTS)))
        sys.exit(1)

    if args.gift:
        run_gift_test(args.variant, args.repeats, args.url, args.verbose)
    else:
        run_test(args.variant, args.repeats, args.url, args.verbose)
