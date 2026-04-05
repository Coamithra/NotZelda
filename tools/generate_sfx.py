"""Generate sound effects from text prompts using Meta's AudioGen model.

Reads data/sfx_manifest.json and batch-generates WAV files into music/sfx/.
Requires: pip install audiocraft (PyTorch 2.1+, Python 3.9+)

Usage:
    python tools/generate_sfx.py                  # generate all missing SFX
    python tools/generate_sfx.py --force           # regenerate everything
    python tools/generate_sfx.py --only sword_slash chest_open  # specific keys
    python tools/generate_sfx.py --cpu             # force CPU (slow but works)
    python tools/generate_sfx.py --list            # show manifest without generating
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "data" / "sfx_manifest.json"
OUTPUT_DIR = ROOT / "music" / "sfx"


def load_manifest() -> dict:
    with open(MANIFEST_PATH, "r") as f:
        data = json.load(f)
    # Strip metadata keys
    return {k: v for k, v in data.items() if not k.startswith("_")}


def list_manifest(manifest: dict) -> None:
    """Print the manifest in a readable table."""
    print(f"\n{'Name':<20} {'Category':<12} {'Duration':>8}  Prompt")
    print("-" * 80)
    for name, entry in sorted(manifest.items()):
        cat = entry.get("category", "?")
        dur = entry.get("duration", "auto")
        prompt = entry["prompt"]
        print(f"{name:<20} {cat:<12} {dur:>6}s  {prompt}")
    print(f"\nTotal: {len(manifest)} sound effects")


def output_path(name: str, category: str) -> Path:
    """Return the output WAV path for a given SFX entry."""
    cat_dir = OUTPUT_DIR / category
    cat_dir.mkdir(parents=True, exist_ok=True)
    return cat_dir / f"{name}.wav"


def generate(manifest: dict, force: bool, only: list[str] | None, use_cpu: bool) -> None:
    # Filter to requested keys
    if only:
        missing = [k for k in only if k not in manifest]
        if missing:
            print(f"Error: unknown manifest keys: {', '.join(missing)}")
            sys.exit(1)
        manifest = {k: manifest[k] for k in only}

    # Skip already-generated unless --force
    if not force:
        before = len(manifest)
        manifest = {
            k: v for k, v in manifest.items()
            if not output_path(k, v.get("category", "misc")).exists()
        }
        skipped = before - len(manifest)
        if skipped:
            print(f"Skipping {skipped} already-generated SFX (use --force to regenerate)")

    if not manifest:
        print("Nothing to generate.")
        return

    print(f"\nGenerating {len(manifest)} sound effects...\n")

    # Lazy-import heavy deps so --list and --help stay fast
    try:
        import torch
        import torchaudio
        from audiocraft.models import AudioGen
    except ImportError:
        print("Error: audiocraft not installed. Run:")
        print("  pip install audiocraft")
        sys.exit(1)

    # Device selection
    if use_cpu:
        device = "cpu"
    elif torch.cuda.is_available():
        device = "cuda"
        vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
        print(f"GPU: {torch.cuda.get_device_name(0)} ({vram_gb:.1f} GB VRAM)")
    else:
        device = "cpu"
        print("No CUDA GPU detected, falling back to CPU (this will be slow)")

    print(f"Device: {device}")
    print("Loading AudioGen model (facebook/audiogen-medium)...")
    t0 = time.time()
    model = AudioGen.get_pretrained("facebook/audiogen-medium", device=device)
    print(f"Model loaded in {time.time() - t0:.1f}s\n")

    # Generate one at a time so we can set per-item duration
    for name, entry in manifest.items():
        prompt = entry["prompt"]
        duration = entry.get("duration", 3)
        category = entry.get("category", "misc")
        out = output_path(name, category)

        print(f"  {name} ({duration}s) — \"{prompt}\"")
        model.set_generation_params(duration=duration)

        t1 = time.time()
        wav = model.generate([prompt])
        elapsed = time.time() - t1

        torchaudio.save(str(out), wav[0].cpu(), model.sample_rate)
        size_kb = out.stat().st_size / 1024
        print(f"    -> {out.relative_to(ROOT)} ({size_kb:.0f} KB, {elapsed:.1f}s)")

    print(f"\nDone! Files in {OUTPUT_DIR.relative_to(ROOT)}/")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate game SFX from text prompts via AudioGen")
    parser.add_argument("--force", action="store_true", help="Regenerate even if file exists")
    parser.add_argument("--only", nargs="+", metavar="KEY", help="Only generate these manifest keys")
    parser.add_argument("--cpu", action="store_true", help="Force CPU inference (slow)")
    parser.add_argument("--list", action="store_true", help="List manifest entries without generating")
    args = parser.parse_args()

    manifest = load_manifest()

    if args.list:
        list_manifest(manifest)
        return

    generate(manifest, force=args.force, only=args.only, use_cpu=args.cpu)


if __name__ == "__main__":
    main()
