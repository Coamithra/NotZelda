# llama3.2:3b NPC Chat Evaluation

**Date:** 2026-04-09
**Model:** llama3.2:3b (Q4_K_M, 2.0 GB, 3.2B params)
**Test tool:** `tools/test_npc_prompts.py` with model verification
**Hardware:** RTX 4070 Ti (12GB VRAM), local Ollama

---

## Summary

Evaluated llama3.2:3b as a potential replacement for gemma2:2b for NPC chat on the Hetzner CX22. Tested 6 prompt strategies across guard classification and gift mechanics. **llama3.2 is a significantly better guard classifier but fundamentally cannot handle the gift mechanic at 3B parameters**, regardless of prompt structure.

**Decision: keep gemma2:2b.** The gift mechanic is a core gameplay feature and llama3.2 can't do it reliably.

---

## Approaches Tested

### 1. Tag-based prompts (variants 0-8, existing)

Previous testing (see REPORT_GEMMA3_MODEL_COMPARISON.md) showed llama3.2 with forced-choice tags:
- Guard FP: 7.5% (excellent, vs gemma2's 32.8%)
- Guard TP: 66.7%
- Gift TP: 0% (completely broken)

The model treats `[GIVE_ITEM]` as a mood label and always picks `[FRIENDLY]` instead.

### 2. Ollama native tool calling (variants 9-10)

Defined `give_item` and `call_guards` as Ollama tools so the model invokes them as function calls.

- Gift TP: 100% (perfect!)
- Guard TP: 100%
- Guard FP: 86.7% (unusable - calls guards on everything)
- Gift FP: 3.7%

**Problems:**
- Model is over-eager to use tools when they're available
- Responses contain NO dialog text (it's either a tool call or text, never both)
- Model hallucinates parameters even when the tool is defined as parameterless
- Sometimes writes tool calls as literal JSON text instead of invoking them (~15-20% of the time)
- Hallucinated params waste tokens and echo JSON Schema boilerplate

### 3. Hybrid: tags for guards + tool calling for gifts (variant 11)

Split approach: forced-choice text tags for guard classification (which llama3.2 does well) and tool calling only for gift giving.

- Guard FP: 12.2%
- Guard TP: 76.2%
- Gift FP: 0.0%
- Gift TP: 83.3% (with gift context in prompt), but ~15% of calls "narrate" the tool as JSON text

**Problems:**
- Still no dialog when a tool call fires
- Text-JSON narration failures are unpredictable
- Would need fallback parsing of JSON from response text

### 4. Optional tags (variant 12)

Simple rules: "add [CALL_GUARDS] if threatening, add [GIVE_ITEM] if they earned it, otherwise reply normally."

- Guard FP: 7.8% (best overall)
- Guard TP: 76.2%
- Gift FP: 1.9%
- Gift TP: 16.7% (poor)

Great guard classification, natural dialog, but almost never uses `[GIVE_ITEM]`. The model narratively gives items ("here's a sword worthy of your bravery!") without the tag.

### 5. Binary GIVE/DENY forced choice

Only two options: `[GIVE_ITEM]` or `[DENY]`. Forces the model to make a yes/no decision.

- Gift TP: ~100% on smith_brave_quest scenario (3/3 in quick test)
- But: can't handle guard classification in the same prompt
- Gift FP: 29.6% when combined with guards (over-gives on casual messages)
- Pollutes dialog: every response becomes about swords even for "Hello there!"

### 6. Two-pass: roleplay then followup question

Let the model roleplay freely, then ask "Did you just give away your [item] in your last response? Answer only YES or NO."

- Gift TP: 67% (with item-specific question)
- Gift FP: 15% (Barmaid too agreeable, says YES to casual messages)
- Smith too conservative (says NO even when narratively giving a sword)
- Doubles API calls for gift NPCs
- Clean YES/NO responses (no bizarre output)

---

## Core Finding

llama3.2:3b understands gift-worthy moments at a narrative level but cannot reliably express that understanding through any structured format - text tags, tool calls, binary choices, or post-hoc self-assessment. This is a fundamental limitation at 3B parameters.

The model treats tags as flavor/mood indicators rather than game actions. When forced to choose, it either over-triggers or the prompt structure pollutes the dialog quality. Tool calling works mechanically but produces no dialog and hallucinates parameters.

## Comparison Table

| Approach | Guard FP | Guard TP | Gift FP | Gift TP | Dialog Quality |
|----------|----------|----------|---------|---------|---------------|
| forced-choice tags | 7.5% | 66.7% | 0.9% | 0% | Good |
| full tool calling | 86.7% | 100% | 3.7% | 100% | None (empty) |
| hybrid (tags+tools) | 12.2% | 76.2% | 0% | 83.3% | None on gift |
| optional tags | 7.8% | 76.2% | 1.9% | 16.7% | Best |
| binary GIVE/DENY | 26.7% | 95.2% | 29.6% | 33% | Polluted |
| two-pass followup | ~8% | ~76% | ~15% | 67% | Good (2x calls) |
| **gemma2:2b (current)** | **32.8%** | **90.5%** | **9.3%** | **88.9%** | **Good** |

## What llama3.2 IS Good For

If the game ever drops the gift mechanic or moves gift decisions to a separate system, llama3.2 would be a meaningful upgrade for guard classification alone:
- 7.5-7.8% guard FP vs gemma2's 32.8%
- With 2-strike system: ~0.6% effective false summon rate vs ~10.8%
- Fits on the CX22 at 2.0 GB
- Natural, high-quality dialog

## Reproducibility

Variants 9-12 are implemented in `test_npc_prompts.py` and can be rerun with `--variant N --model llama3.2:3b`. The binary GIVE/DENY and two-pass followup experiments (approaches 5-6) were ad-hoc scripts run during the evaluation session - their results are preserved in the log files below but don't have reusable test harness code.

## Test Artifacts

Full verbose logs with complete request/response JSON in `docs/`:
- `test_results_llama3_2_3b_gift_tp.txt` - all 9 original variants, gift TP
- `test_results_llama3_2_3b_guard.txt` - forced-choice guard test
- `test_results_llama3_2_3b_toolcall_gift.txt` - tool calling gift TP
- `test_results_llama3_2_3b_toolcall_guard.txt` - tool calling guard test
- `test_results_llama3_2_3b_tcstrict_guard.txt` - strict tool calling guard
- `test_results_llama3_2_3b_hybrid_guard.txt` - hybrid guard test
- `test_results_llama3_2_3b_hybrid_gift_v2.txt` - hybrid gift TP (with context)
- `test_results_llama3_2_3b_optional_tags_guard.txt` - optional tags guard
- `test_results_llama3_2_3b_optional_tags_gift.txt` - optional tags gift TP
- `full_log_optional_tags_gift.txt` - full request/response, optional tags gift
- `full_log_optional_tags_guard.txt` - full request/response, optional tags guard
- `full_log_binary_give_deny.txt` - full request/response, binary GIVE/DENY
- `full_log_two_pass.txt` - full request/response, two-pass followup
- `give_item_prompt_comparison.txt` - prompt variant A/B/C comparison
- `hybrid_gift_full_conversations.txt` - full conversations, hybrid gift
- `single_call_debug.txt` - single call debug output
