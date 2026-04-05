"""Generate multiple variations of each SFX for A/B audition testing.

Reads data/sfx_manifest.json and generates N variations per entry (default 6)
into audio/sfx/_variants/. Use the audition server to pick favorites.

Requires: pip install audiocraft (PyTorch 2.1+, Python 3.9+)

Usage:
    python tools/generate_sfx_variants.py                # generate all missing
    python tools/generate_sfx_variants.py --force         # regenerate everything
    python tools/generate_sfx_variants.py --only sword_slash chest_open
    python tools/generate_sfx_variants.py --cpu           # force CPU (slow)
    python tools/generate_sfx_variants.py -n 3            # 3 variants instead of 6
    python tools/generate_sfx_variants.py --list          # preview without generating
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "data" / "sfx_manifest.json"
VARIANTS_DIR = ROOT / "audio" / "sfx" / "_variants"
DEFAULT_NUM_VARIANTS = 6


def load_manifest() -> dict:
    with open(MANIFEST_PATH, "r") as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if not k.startswith("_")}


def list_manifest(manifest: dict, num_variants: int) -> None:
    print(f"\n{'Name':<20} {'Category':<12} {'Duration':>8}  Prompt")
    print("-" * 80)
    for name, entry in sorted(manifest.items()):
        cat = entry.get("category", "?")
        dur = entry.get("duration", "auto")
        prompt = entry["prompt"]
        print(f"{name:<20} {cat:<12} {dur:>6}s  {prompt}")
    total_files = len(manifest) * num_variants
    print(f"\nTotal: {len(manifest)} sounds × {num_variants} variants = {total_files} files")


def variant_path(name: str, variant_num: int) -> Path:
    return VARIANTS_DIR / f"{name}_v{variant_num}.wav"


def generate(manifest: dict, force: bool, only: list[str] | None,
             use_cpu: bool, num_variants: int) -> None:
    if only:
        missing = [k for k in only if k not in manifest]
        if missing:
            print(f"Error: unknown manifest keys: {', '.join(missing)}")
            sys.exit(1)
        manifest = {k: manifest[k] for k in only}

    # Build work list: (name, entry, variant_num) for all needed generations
    work = []
    for name, entry in manifest.items():
        for v in range(1, num_variants + 1):
            out = variant_path(name, v)
            if out.exists() and not force:
                continue
            work.append((name, entry, v))

    skipped = len(manifest) * num_variants - len(work)
    if skipped and not force:
        print(f"Skipping {skipped} already-generated variants (use --force to regenerate)")

    if not work:
        print("Nothing to generate.")
        return

    VARIANTS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\nGenerating {len(work)} variant files "
          f"({len(manifest)} sounds × up to {num_variants} variants)...\n")

    # Lazy-import heavy deps
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

    current_name = None
    gen_count = 0
    total_time = 0

    for name, entry, v in work:
        if name != current_name:
            current_name = name
            prompt = entry["prompt"]
            duration = entry.get("duration", 3)
            print(f"  {name} ({duration}s) — \"{prompt}\"")
            model.set_generation_params(duration=duration)

        out = variant_path(name, v)
        t1 = time.time()
        wav = model.generate([entry["prompt"]])
        elapsed = time.time() - t1
        total_time += elapsed

        torchaudio.save(str(out), wav[0].cpu(), model.sample_rate)
        size_kb = out.stat().st_size / 1024
        gen_count += 1
        print(f"    v{v} -> {out.name} ({size_kb:.0f} KB, {elapsed:.1f}s)")

    print(f"\nDone! Generated {gen_count} files in {total_time:.1f}s")
    print(f"Variants in: {VARIANTS_DIR.relative_to(ROOT)}/")
    print(f"\nNext step: python tools/sfx_audition_server.py")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate SFX variants for A/B audition testing")
    parser.add_argument("--force", action="store_true",
                        help="Regenerate even if files exist")
    parser.add_argument("--only", nargs="+", metavar="KEY",
                        help="Only generate these manifest keys")
    parser.add_argument("--cpu", action="store_true",
                        help="Force CPU inference (slow)")
    parser.add_argument("-n", "--num-variants", type=int,
                        default=DEFAULT_NUM_VARIANTS,
                        help=f"Variants per sound (default: {DEFAULT_NUM_VARIANTS})")
    parser.add_argument("--list", action="store_true",
                        help="List manifest entries without generating")
    args = parser.parse_args()

    manifest = load_manifest()

    if args.list:
        list_manifest(manifest, args.num_variants)
        return

    generate(manifest, force=args.force, only=args.only,
             use_cpu=args.cpu, num_variants=args.num_variants)


if __name__ == "__main__":
    main()
