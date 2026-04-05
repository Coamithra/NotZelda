"""Apply audition selections: copy chosen variants to final SFX locations.

Reads data/sfx_selection.json (written by the audition server) and copies
each selected variant WAV to its final location in audio/sfx/{category}/.

Usage:
    python tools/apply_sfx_selection.py            # apply selections
    python tools/apply_sfx_selection.py --dry-run   # preview without copying
"""

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "data" / "sfx_manifest.json"
SELECTION_PATH = ROOT / "data" / "sfx_selection.json"
VARIANTS_DIR = ROOT / "audio" / "sfx" / "_variants"
OUTPUT_DIR = ROOT / "audio" / "sfx"


def main() -> None:
    dry_run = "--dry-run" in sys.argv

    if not SELECTION_PATH.exists():
        print(f"Error: {SELECTION_PATH.relative_to(ROOT)} not found.")
        print("Run the audition server first: python tools/sfx_audition_server.py")
        sys.exit(1)

    with open(MANIFEST_PATH) as f:
        manifest = {k: v for k, v in json.load(f).items() if not k.startswith("_")}

    with open(SELECTION_PATH) as f:
        selection = json.load(f)

    if not selection:
        print("No selections found in file.")
        sys.exit(1)

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Applying {len(selection)}/{len(manifest)} SFX selections:\n")

    copied = 0
    errors = 0

    for name, variant_num in sorted(selection.items()):
        if name not in manifest:
            print(f"  SKIP {name} — not in manifest")
            errors += 1
            continue

        category = manifest[name].get("category", "misc")
        src = VARIANTS_DIR / f"{name}_v{variant_num}.wav"
        dst_dir = OUTPUT_DIR / category
        dst = dst_dir / f"{name}.wav"

        if not src.exists():
            print(f"  ERROR {name} v{variant_num} — variant file missing: {src.name}")
            errors += 1
            continue

        size_kb = src.stat().st_size / 1024
        action = "would copy" if dry_run else "copied"

        if not dry_run:
            dst_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

        print(f"  {name} v{variant_num} -> {dst.relative_to(ROOT)} ({size_kb:.0f} KB) [{action}]")
        copied += 1

    # Report unselected sounds
    unselected = [n for n in manifest if n not in selection]
    if unselected:
        print(f"\n  Not selected ({len(unselected)}): {', '.join(sorted(unselected))}")

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Done: {copied} copied, {errors} errors, {len(unselected)} unselected")

    if not dry_run and copied > 0:
        print(f"\nSFX files ready in {OUTPUT_DIR.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
