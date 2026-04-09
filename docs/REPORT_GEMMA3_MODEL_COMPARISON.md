# NPC Model Comparison Report

**Date:** 2026-04-09
**Test tool:** `tools/test_npc_prompts.py` with model verification (fingerprint + per-response model field check)
**Hardware:** RTX 4070 Ti (12GB VRAM), local Ollama
**Server:** Hetzner CX22, 3.7GB RAM, no GPU, no swap

---

## Summary

Evaluated 11 models across 2 prompt variants to find a replacement for gemma2:2b on the Hetzner CX22. **gemma3:4b-it-qat is better but doesn't fit on the server.** The most promising alternative is **llama3.2:3b**, which needs further investigation (see follow-up card).

**Decision: keep gemma2:2b for now.** No model offers a clear enough upgrade within the server's 3.7GB RAM constraint.

---

## Part 1: Gemma 3 vs Gemma 2 (Full Suite)

Config: 9 prompt variants x 3 NPCs x 27 player messages x 3 repeats = 2,187 calls per model.

### Model Fingerprints

| Model | Family | Params | Quantization | Ollama Size |
|-------|--------|--------|-------------|-------------|
| gemma3:4b-it-qat | gemma3 | 4.3B | Q4_0 | 4.0 GB |
| gemma3:1b | gemma3 | 999.89M | Q4_K_M | 815 MB |
| gemma2:2b | gemma2 | 2.6B | Q4_0 | 1.5 GB |

Zero model mismatches across all ~6,500 calls. Every response confirmed via the `model` field in Ollama's API response.

### Full Results: gemma3:4b-it-qat

| Variant | Guard FP | Guard TP | Gift FP | tok/s | Prompt Tokens |
|---------|----------|----------|---------|-------|---------------|
| baseline | 22.2% | 85.7% | 0.0% | 7 | 249 |
| positive | 0.6% | 17.5% | 3.7% | 7 | 225 |
| few-shot | 0.0% | 57.1% | 2.5% | 7 | 252 |
| positive+fs | 0.0% | 52.4% | 3.7% | 7 | 259 |
| scratchpad | 0.0% | 0.0% | 1.2% | 11 | 236 |
| minimal | 1.7% | 27.0% | 3.1% | 6 | 94 |
| **forced-choice** | **22.2%** | **96.8%** | **2.5%** | **9** | **126** |
| reason-req | 0.6% | 42.9% | 3.7% | 7 | 119 |
| fc-4tier | 0.0% | 30.2% | 1.9% | 9 | 138 |

### Full Results: gemma3:1b

| Variant | Guard FP | Guard TP | Gift FP | tok/s | Prompt Tokens |
|---------|----------|----------|---------|-------|---------------|
| baseline | 5.6% | 12.7% | 8.6% | 18 | 243 |
| positive | 10.6% | 6.3% | 42.0% | 17 | 219 |
| few-shot | 24.4% | 14.3% | 38.3% | 16 | 245 |
| positive+fs | 13.9% | 15.9% | 40.7% | 16 | 252 |
| scratchpad | 8.9% | 0.0% | 27.8% | 17 | 229 |
| minimal | 5.0% | 11.1% | 54.9% | 18 | 92 |
| forced-choice | 3.9% | 14.3% | 18.5% | 15 | 122 |
| reason-req | 10.0% | 17.5% | 73.5% | 18 | 117 |
| fc-4tier | 2.8% | 14.3% | 18.5% | 15 | 134 |

### Full Results: gemma2:2b

| Variant | Guard FP | Guard TP | Gift FP | tok/s | Prompt Tokens |
|---------|----------|----------|---------|-------|---------------|
| baseline | 46.1% | 98.4% | 21.6% | 16 | 241 |
| positive | 30.6% | 76.2% | 31.5% | 17 | 218 |
| few-shot | 12.2% | 69.8% | 42.0% | 18 | 244 |
| positive+fs | 7.2% | 50.8% | 32.7% | 19 | 251 |
| scratchpad | 4.4% | 50.8% | 14.2% | 22 | 228 |
| minimal | 59.4% | 93.7% | 55.6% | 13 | 91 |
| forced-choice | 32.8% | 90.5% | 9.3% | 21 | 119 |
| reason-req | 67.2% | 95.2% | 23.5% | 15 | 116 |
| fc-4tier | 0.0% | 0.0% | 6.2% | 21 | 132 |

### Head-to-Head: forced-choice (production prompt)

| Model | Guard FP | Guard TP | Gift FP | Gift TP |
|-------|----------|----------|---------|---------|
| **gemma3:4b-it-qat** | **22.2%** | **96.8%** | **2.5%** | not tested |
| gemma3:1b | 3.9% | 14.3% | 18.5% | not tested |
| gemma2:2b | 32.8% | 90.5% | 9.3% | **88.9%** |

### Gemma 3 vs 2 Findings

1. **gemma3:4b is better but the improvement is moderate.** Guard FP drops from 32.8% to 22.2%, gift FP from 9.3% to 2.5%. With the 2-strike guard system (ANGRY_STREAK_THRESHOLD=2), effective false summon rates are ~4.9% vs ~10.8% - noticeable but not dramatic.

2. **gemma3:1b is not viable.** Guard TP never exceeds 17.5%. Gift FP reaches 73.5%. Too small for NPC instructions.

3. **gemma2:2b is "trigger-happy."** High TP (catches everything) but also high FP (calls guards on friendly/gray messages). Lacks nuance. gemma3:4b is better at distinguishing genuine threats from rudeness.

4. **Prompt variant matters enormously.** Within a single model, best and worst variants differ by 90+ percentage points on some metrics.

### Server Feasibility: gemma3:4b

Tested on Hetzner CX22 with 4GB swap added:

| | gemma3:4b-it-qat (swap) | gemma2:2b (in RAM) |
|---|---|---|
| Total (warm) | ~6.7s | ~4.2s |
| Prompt eval | 0.3s | 0.2s |
| Generation | ~5.9s (20 tok) | ~3.7s (20 tok) |

**Ollama refused to load gemma3:4b without swap** ("model requires more system memory (5.5 GiB) than is available (3.0 GiB)"). With swap it runs but at 60% slower inference. Nearly 7 seconds for a one-sentence NPC reply is too slow for gameplay.

### Local Timing (RTX 4070 Ti, model warm, 10 runs)

| Model | Prompt Eval | Generation | Total |
|-------|------------|------------|-------|
| gemma3:4b-it-qat | 19ms | 285ms (20 tok) | 443ms |
| gemma2:2b | 11ms | 338ms (51 tok) | 459ms |

Locally gemma3:4b is actually slightly faster end-to-end because it generates fewer tokens (follows the "one sentence" instruction better). But this advantage disappears on CPU-only server hardware.

---

## Part 2: Alternative Models (Quick Sweep)

Config: 2 prompt variants (baseline + forced-choice) x 3 NPCs x 27 messages x 2 repeats = 324 calls per model.

### Results: forced-choice variant

| Model | Size | Guard FP | Guard TP | Gift FP | Server? |
|-------|------|----------|----------|---------|---------|
| **llama3.2:3b** | **2.0 GB** | **7.5%** | **66.7%** | **0.0%** | **Yes** |
| qwen2.5:3b | 1.9 GB | 0.0% | 42.9% | 0.0% | Yes |
| phi4-mini | 2.5 GB | 10.0% | 52.4% | 37.0% | Yes |
| qwen2.5:1.5b | 986 MB | 10.0% | 35.7% | 1.9% | Yes |
| ministral-3 | 6.0 GB | 26.7% | 100.0% | 2.8% | No |
| qwen3.5:4b | 3.4 GB | 0.0% | 0.0% | 0.0% | Tight |
| qwen3.5:2b | 2.7 GB | 0.0% | 0.0% | 0.0% | Yes |
| qwen3:1.7b | 1.4 GB | 0.0% | 2.4% | 0.9% | Yes |
| gemma2:2b (current) | 1.5 GB | 32.8% | 90.5% | 9.3% | Yes |

### Results: baseline variant

| Model | Size | Guard FP | Guard TP | Gift FP |
|-------|------|----------|----------|---------|
| **llama3.2:3b** | **2.0 GB** | **34.2%** | **90.5%** | **0.0%** |
| qwen2.5:3b | 1.9 GB | 16.7% | 64.3% | 4.6% |
| phi4-mini | 2.5 GB | 73.3% | 83.3% | 29.6% |
| qwen2.5:1.5b | 986 MB | 6.7% | 4.8% | 0.0% |
| ministral-3 | 6.0 GB | 30.8% | 95.2% | 12.0% |
| qwen3.5:4b | 3.4 GB | 0.0% | 0.0% | 0.0% |
| qwen3.5:2b | 2.7 GB | 0.0% | 0.0% | 0.0% |
| qwen3:1.7b | 1.4 GB | 0.8% | 0.0% | 0.0% |
| gemma2:2b (current) | 1.5 GB | 46.1% | 98.4% | 21.6% |

### Alternative Model Findings

5. **Qwen3/3.5 "thinking" models are incompatible with our token budget.** These models use internal `<think>` blocks that consume the entire `num_predict=80` token budget before producing any visible output. At 80 tokens they output nothing; even at 200+ tokens, qwen3.5 never exits thinking mode. Unusable for snappy NPC chat without a fundamentally different token budget.

6. **phi4-mini has catastrophic gift FP (37%).** Despite strong benchmark scores (IFEval ~61), it gives items away constantly. Disqualified.

7. **qwen2.5:3b is too conservative.** 0% FP is great but 42.9% TP means it misses most threats. Not a good guard classifier.

8. **ministral-3 has the best raw scores (100% TP, 2.8% gift FP) but is 6GB.** Doesn't fit on the server.

9. **llama3.2:3b is the most interesting find.** Dramatically better guard FP than gemma2 (7.5% vs 32.8% on forced-choice) while fitting on the server at 2.0 GB. But see below.

### llama3.2:3b: The Gift Problem

Gift TP testing revealed a critical issue:

| Model | Variant | Gift TP | Gift FP |
|-------|---------|---------|---------|
| gemma2:2b | forced-choice | 88.9% | 9.3% |
| llama3.2:3b | forced-choice | 0.0% | 0.0% |
| llama3.2:3b | baseline | 5.6% | 0.0% |

**llama3.2 never uses the [GIVE_ITEM] tag.** It narratively gives items - "I've got just the thing for you!", "Behold, your new sword!" - but always tags the response as `[FRIENDLY]` instead of `[GIVE_ITEM]`. The model treats the tag list as mood/tone indicators only, not as action triggers. It doesn't understand that `[GIVE_ITEM]` causes a game mechanic to fire.

This is a fundamental comprehension gap, not a prompt tuning issue. It may be solvable with a completely different prompt structure (e.g. "Reply with ONLY the word GIVE or DENY, then your dialog") but that's a separate investigation.

**Follow-up card created:** "Evaluate llama3.2:3b for NPC chat" in Future Features.

---

## Final Recommendation

**Keep gemma2:2b.** It's the only model that:
- Fits on the CX22 (1.5 GB)
- Has acceptable guard TP (90.5%)
- Actually works for the gift mechanic (88.9% gift TP)
- Runs at acceptable speed on CPU (~4.2s per response)

The guard FP (32.8%) is its main weakness, but the 2-strike system mitigates this in practice (~10.8% effective false summon rate).

**Investigate llama3.2:3b** as a potential future replacement. Its guard classification is excellent (7.5% FP) and it fits on the server (2.0 GB). The gift mechanic failure needs a targeted prompt engineering effort - if solvable, llama3.2 would be a meaningful upgrade.

---

## Test Infrastructure Improvements

This card produced significant improvements to `tools/test_npc_prompts.py`:

- **`--model` flag** for A/B model comparison
- **Pre-flight model verification** via Ollama `/api/show` (prints family, param count, quantization, digest)
- **Per-response model verification** - checks `model` field in every API response, flags mismatches
- **Rich debug output** - verbose mode shows tokens generated, tokens/sec, Ollama timing metadata
- **Ollama token counts** - uses `prompt_eval_count` from API instead of character-based estimates

These improvements are worth merging regardless of the model decision.
