#!/usr/bin/env python3
"""Generate WebP + optimized JPEG variants for every photo in photos/.

For each source file, two outputs land in photos-web/:
  - <stem><source-suffix>  — re-encoded JPEG, max 1500 px long edge, q=82
  - <stem>.webp            — WebP, max 1500 px long edge, q=80

Idempotent — skips files where both outputs are newer than the source.
A manifest.json records each output's pixel dimensions so the HTML can
carry width/height attributes and avoid CLS.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
SRC = ROOT / "photos"
OUT = ROOT / "photos-web"
MANIFEST = OUT / "manifest.json"

MAX_SIDE = 1500
JPEG_Q = 82
WEBP_Q = 80


def main() -> int:
    try:
        from PIL import Image  # type: ignore
    except ImportError:
        sys.exit("✗ Pillow not installed. Install with:  pip3 install Pillow")

    OUT.mkdir(exist_ok=True)
    manifest: dict = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}

    sources = sorted(
        p for p in SRC.iterdir()
        if p.suffix.lower() in (".jpg", ".jpeg") and not p.name.startswith(".")
    )

    built, kept = 0, 0
    for src in sources:
        out_jpg = OUT / src.name
        out_webp = OUT / f"{src.stem}.webp"

        if (out_jpg.exists() and out_webp.exists()
                and out_jpg.stat().st_mtime >= src.stat().st_mtime
                and out_webp.stat().st_mtime >= src.stat().st_mtime
                and src.name in manifest):
            kept += 1
            continue

        img = Image.open(src)
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        w, h = img.size
        scale = min(MAX_SIDE / max(w, h), 1.0)
        if scale < 1.0:
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        ow, oh = img.size

        img.save(out_jpg, "JPEG", quality=JPEG_Q, optimize=True, progressive=True)
        img.save(out_webp, "WEBP", quality=WEBP_Q, method=6)

        manifest[src.name] = {"width": ow, "height": oh}
        built += 1
        sj = out_jpg.stat().st_size // 1024
        sw = out_webp.stat().st_size // 1024
        print(f"  + {src.name}  {ow}×{oh}  jpg {sj} KB · webp {sw} KB")

    # Prune orphaned manifest entries + output files.
    expected = {"manifest.json"}
    for s in sources:
        expected.add(s.name)
        expected.add(f"{s.stem}.webp")
    for out in OUT.iterdir():
        if out.name not in expected:
            out.unlink()
            print(f"  - removed orphan {out.name}")
    for k in list(manifest):
        if k not in {s.name for s in sources}:
            manifest.pop(k)

    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"built {built}, kept {kept}; manifest at {MANIFEST.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
