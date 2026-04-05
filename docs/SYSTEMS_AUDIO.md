# Audio & Sound Effects

## Overview

Game audio lives in `music/` organized by area. Background music is hand-picked MP3s. Sound effects are AI-generated using Meta's [AudioGen](https://github.com/facebookresearch/audiocraft) model (1.5B params), run locally on GPU.

## Directory Layout

```
music/
├── overworld/          # Overworld area BGM (MP3)
├── dungeon1/           # Dungeon 1 BGM
├── dungeon2/           # Dungeon 2 BGM
├── dungeon3/           # Dungeon 3 BGM
├── other/              # Misc BGM
└── sfx/                # AI-generated sound effects (WAV)
    ├── combat/         # sword_slash, sword_hit, player_hurt, monster_death, boss_roar
    ├── environment/    # door_open, door_locked, footsteps, water_splash, portal_enter
    ├── items/          # chest_open, key_pickup, item_pickup
    └── ui/             # npc_chat_open
```

## SFX Generation Pipeline

### Manifest

All sound effects are declared in `data/sfx_manifest.json`. Each entry has:

```json
{
    "sword_slash": {
        "prompt": "sharp sword slash swoosh through air",
        "duration": 1,
        "category": "combat"
    }
}
```

- **prompt** — text description fed to AudioGen
- **duration** — length in seconds (0.5-10 recommended)
- **category** — subdirectory under `music/sfx/`

To add a new sound effect, add an entry to the manifest and re-run the generator.

### Generator Tool

```bash
python tools/generate_sfx.py              # generate all missing SFX
python tools/generate_sfx.py --force      # regenerate everything
python tools/generate_sfx.py --only sword_slash chest_open   # specific keys
python tools/generate_sfx.py --cpu        # force CPU (very slow)
python tools/generate_sfx.py --list       # preview manifest, no generation
```

The tool skips already-generated files by default. Use `--force` to overwrite.

### Model Details

- **Model**: `facebook/audiogen-medium` (1.5B parameters)
- **Output**: 16kHz mono WAV
- **Weights**: ~3.5GB, downloaded once to `~/.cache/huggingface/` on first run
- **GPU**: ~2-3 seconds per effect on RTX 4070 Ti (12GB VRAM)
- **CPU**: Works but very slow and CPU-intensive — avoid unless necessary

### Dependencies

SFX generation requires `audiocraft` and its dependencies (PyTorch, torchaudio, xformers). These are dev-only dependencies, not needed to run the game server.

```bash
pip install audiocraft
```

On Windows, `audiocraft` pins old versions of `av` and `torch` that don't have prebuilt wheels. The workaround:

```bash
pip install av                          # get prebuilt wheel (v17+)
pip install audiocraft --no-deps        # install audiocraft without its pinned deps
pip install flashy hydra-core hydra_colorlog julius num2words sentencepiece spacy torchaudio encodec librosa torchmetrics
pip install xformers --index-url https://download.pytorch.org/whl/cu124   # match your CUDA version
```

Pip will warn about version mismatches — these are cosmetic; everything works with newer versions.

## Prompt Tips

AudioGen responds best to concrete, descriptive prompts:

- Good: `"heavy wooden door creaking open slowly"`
- Bad: `"door sound"`
- Good: `"metal sword hitting metal armor clang impact"`
- Bad: `"sword hit"`

Keep prompts under ~15 words. Multiple descriptors (material, action, quality) help. The model is trained on environmental/foley sounds — it handles impacts, footsteps, doors, water, and ambient noise well. It's weaker on musical/tonal sounds (chimes, UI bleeps) where results may need more iteration.
