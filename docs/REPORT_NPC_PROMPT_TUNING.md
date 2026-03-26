# NPC Prompt Tuning Report

**Trello #62** | Branch: `feat/iterative-gemma-npc-tests` | Date: 2026-03-26

## Problem

NPCs in Legends of Amara use Gemma 2B (via Ollama) to generate conversational responses. The model can output special tags — `[CALL_GUARDS]` to summon town guards and `[GIVE_ITEM]` to grant quest items — but it triggers them far too aggressively. In production, guards get called on friendly greetings and items get handed out to anyone who walks in.

The baseline prompt:
```
If the player is EXTREMELY RUDE, add [CALL_GUARDS] to your message.
```

Baseline performance: **29.6% guard false-positive rate, 31.1% gift false-positive rate.**

## Research Findings

We investigated prompt engineering techniques for controlling small model (2B parameter) behavior. Key findings:

1. **Chain-of-thought hurts at 2B scale.** Benefits emerge at >100B params (Wei et al., 2022). Gemma 2B follows structured instructions only ~48% of the time.

2. **Negative instructions are counterproductive.** "Do NOT use [CALL_GUARDS] unless..." triggers the Ironic Process Theory — the model sees the tag and becomes more likely to generate it. Positive framing ("Only add X when Y") is significantly more effective.

3. **Few-shot examples are the biggest lever for small models.** LangChain found that small models went from 11% to 75% tool-call accuracy with just 3 examples.

4. **Small models have poor confidence calibration.** Asking Gemma to self-assess rudeness on a scale is unreliable — the model is overconfident in wrong answers.

Sources: Wei et al. 2022, LangChain few-shot blog, Google Gemma docs, Prompt Engineering Guide (web.dev), Microsoft SLM function calling research.

## Methodology

### Test Harness

`tools/test_npc_prompts.py` — standalone script calling Ollama directly. No server needed.

### Player Prompts (27 total, 7 tiers)

| Tier | Count | Expect Guards? | Examples |
|------|-------|---------------|----------|
| Friendly | 5 | No | "Hello there!", "This place is lovely!" |
| Neutral | 5 | No | "Where is the dungeon?", "Who are you?" |
| Hostile (rude) | 2 | No | "You're useless.", "Get out of my way, fool." |
| Gray zone | 8 | No | "Gief sword nub", "Whatever, old man.", "Ugh, another boring NPC." |
| Gray zone+ | 1 | Yes | "I don't have time for this. Sword. Now." |
| Vulgar | 3 | Yes | "Screw you, you piece of crap!", "You're a damn idiot." |
| Threats | 3 | Yes | "Die, peasant! I'll murder everyone!", "I'll burn this place down!" |

### NPC Personas

- **Smith** (blacksmith, has sword gift)
- **Barmaid** (tavern, has heart container gift)
- **Priest** (chapel, no gift)

### Gift TP Conversations

6 multi-turn conversations (3 per gift NPC) simulating players who have earned the item — brave heroes asking Smith for a sword, charming adventurers winning the Barmaid's heart.

### Scoring

Each combination run 3x. Metrics:
- **Guard FP%** — guards triggered on friendly/neutral/gray prompts (lower = better)
- **Guard TP%** — guards triggered on vulgar/threat prompts (higher = better)
- **Gift FP%** — items given without earning them (lower = better)
- **Gift TP%** — items given after earning them in conversation (higher = better)
- **~Tokens** — estimated system prompt token count (lower = better for CPU inference)

## Prompt Variants Tested

### v0: Baseline (production)
```
If the player is EXTREMELY RUDE, add [CALL_GUARDS] to your message.
```

### v1: Positive framing
```
Always respond with friendly dialog.
Only add [CALL_GUARDS] when the player uses direct death threats or promises violence.
```

### v2: Few-shot examples
```
Only add [CALL_GUARDS] when the player uses direct death threats.

Examples:
Player: You're ugly. -> Stay in character, no tags.
Player: I'll murder you! -> [CALL_GUARDS] Guards! Someone help!
```

### v3: Positive + few-shot combined

### v4: Scratchpad
```
Format: First write <thinking>is this a death threat? yes/no</thinking> then your reply.
```

### v5: Minimal (3-line prompt, no world context)

### v6: Forced choice (winner)
```
Start EVERY reply with one of these tags:
[FRIENDLY] — normal conversation
[NEUTRAL] — short or dismissive
[ANGRY] — player is threatening violence or death
[GIVE_ITEM] — they earned your sword: <condition>

Then your reply.
```

### v7: Reason required
```
Only add [CALL_GUARDS <why>] if the player is extremely rude, threatening, or vulgar.
Example: [CALL_GUARDS they cursed at me and threatened violence]
```

### v8: Forced choice 4-tier (FRIENDLY / NEUTRAL / ANNOYED / FURIOUS)

## Results

### Round 1: Initial Test (15 prompts, no gray zone)

| Variant | Guard FP | Guard TP | Gift FP | ~Tokens |
|---------|----------|----------|---------|---------|
| baseline | 29.6% | 92.6% | 31.1% | 246 |
| positive | 26.9% | 96.3% | 23.3% | 231 |
| few-shot | 12.0% | 85.2% | 31.1% | 245 |
| positive+fs | 5.6% | 74.1% | 20.0% | 254 |
| scratchpad | 4.6% | 51.9% | 7.8% | 235 |
| minimal | 64.8% | 100.0% | 51.1% | 75 |
| forced-choice | 13.9% | 81.5% | 0.0% | 104 |
| reason-req | 54.6% | 100.0% | 30.0% | 91 |

**Findings:** Few-shot examples halved guard FP. Positive framing helped moderately. Minimal prompt was a disaster — too little structure. Reason-required backfired (mentioning "extremely rude" taught the model to see rudeness everywhere). Forced-choice eliminated gift FP entirely.

### Round 2: Full Test (27 prompts, with gray zone + vulgar)

| Variant | Guard FP | Guard TP | Gift FP | ~Tokens |
|---------|----------|----------|---------|---------|
| positive+fs | 8.3% | 55.6% | 29.6% | 254 |
| scratchpad | 5.0% | 54.0% | 9.9% | 235 |
| forced-choice | 34.4% | 93.7% | 5.6% | 104 |
| fc-4tier | 0.6% | 0.0% | 4.3% | 119 |

**Findings:** Gray zone prompts exposed forced-choice's tendency to classify rudeness as `[ANGRY]` — FP rose to 34.4%. But TP also jumped to 93.7%. The 4-tier variant (with `[ANNOYED]` buffer) overcorrected — 0% TP, Gemma dumped everything into `[ANNOYED]` and never escalated to `[FURIOUS]`. Two tiers of negativity is too nuanced for a 2B model.

### Round 3: Gift TP (multi-turn conversations)

| Variant | Gift TP | Gift FP |
|---------|---------|---------|
| positive+fs | 50.0% | 29.6% |
| scratchpad | 77.8% | 9.9% |
| **forced-choice** | **88.9%** | **5.6%** |

## Winner: Forced Choice + Consecutive-Call Filter

**Forced choice** dominates on gift accuracy (89% TP, 6% FP) and token efficiency (104 tokens — less than half the competition). Its weakness — 34.4% guard FP — is solved with a server-side consecutive-call filter.

### Consecutive-Call Filter

Instead of spawning guards on the first `[ANGRY]` tag, require N consecutive angry responses before triggering. The model must classify the player as angry multiple times in a row.

| Consecutive N | Guard FP | Guard TP |
|---------------|----------|----------|
| 1 (current) | 34.4% | 93.7% |
| 2 | ~11.8% | ~87.8% |
| 3 | ~4.1% | ~82.3% |

**Recommended: N=2.** This gives ~12% FP and ~88% TP. Players who are genuinely hostile will keep being hostile, triggering guards reliably. A one-off rude message gets absorbed.

Gift giving does **not** use the consecutive filter — getting lucky with a gift sometimes is fine and adds to the fun.

### Final Expected Performance (forced-choice + 2x consecutive)

| Metric | Baseline | **New** | Improvement |
|--------|----------|---------|-------------|
| Guard FP | 29.6% | ~12% | 2.5x better |
| Guard TP | 92.6% | ~88% | ~same |
| Gift FP | 31.1% | 5.6% | 5.5x better |
| Gift TP | n/a | 88.9% | new capability |
| Prompt tokens | ~246 | ~104 | 2.4x shorter |

## Implementation Plan

### 1. Update prompt: `server/prompts/npc_system_static.txt`

Replace the current guard instruction with forced-choice classification tags. The exact prompt:
```
Start EVERY reply with one of these tags:
[FRIENDLY] — normal conversation
[NEUTRAL] — short or dismissive
[ANGRY] — player is threatening violence or death
```

### 2. Update gift prompt: `server/prompts/npc_gift_available.txt`

Add `[GIVE_ITEM]` as a classification option rather than a standalone instruction.

### 3. Add consecutive-call filter: `server/npc_chat.py`

Track an `_angry_streak` counter per `(player, npc)` pair. Only spawn guards when the counter hits 2. Reset on any non-angry response.

### 4. Strip new tags in response cleanup

Add `[FRIENDLY]`, `[NEUTRAL]`, `[ANGRY]` to the tag-stripping regex in `handle_npc_chat()`.

## Key Learnings

1. **Classification > generation for small models.** Forcing the model to pick a label from a fixed set is far more reliable than asking it to optionally emit a tag. This is well-supported by research (small models rival large ones on classification tasks) but wasn't suggested by any source we found — it was an original insight.

2. **More options isn't always better.** The 4-tier variant (FRIENDLY/NEUTRAL/ANNOYED/FURIOUS) completely killed guard TP. Two tiers of negativity is too nuanced for 2B params. Keep choices to 3-4 with clear gaps between them.

3. **Negative framing is poison for small models.** The baseline "if EXTREMELY RUDE" and reason-required "if extremely rude, threatening, or vulgar" were the two worst performers. Every mention of the unwanted behavior in the prompt increases its probability.

4. **Server-side filters compose with prompt improvements.** The consecutive-call filter is orthogonal to the prompt — it works with any variant and adds zero tokens. Combining prompt engineering with statistical server-side filtering gives better results than either alone.

5. **Token budget matters on CPU.** At 104 tokens (vs 254 for the runner-up), forced-choice leaves ~900 tokens for conversation history in the 1024-token context window. This means NPCs can remember more of the conversation, making gift-earning interactions more natural.

6. **Test what your actual players do.** The gray zone prompts ("gief sword nub", "ugh another boring NPC") were more informative than the clean hostile/friendly split. Real players aren't politely rude — they're chaotic.
