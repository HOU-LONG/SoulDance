#!/usr/bin/env python3
from pathlib import Path
from PIL import Image
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
manifest = json.loads((ROOT / "manifest/asset_manifest.json").read_text(encoding="utf-8"))

errors = []
for asset in manifest["assets"]:
    path = ROOT / asset["file"]
    if not path.exists():
        errors.append(f"MISSING: {asset['id']} -> {path}")
        continue
    with Image.open(path) as im:
        has_alpha = "A" in im.getbands() or "transparency" in im.info
        if asset["has_alpha"] != has_alpha:
            errors.append(
                f"ALPHA MISMATCH: {asset['id']} expected={asset['has_alpha']} actual={has_alpha}"
            )
        expected = asset["pixel_size"]
        if im.width != expected["width"] or im.height != expected["height"]:
            errors.append(
                f"SIZE MISMATCH: {asset['id']} expected={expected} actual={im.size}"
            )

if errors:
    print("\n".join(errors))
    sys.exit(1)

print(f"Validated {len(manifest['assets'])} assets successfully.")
