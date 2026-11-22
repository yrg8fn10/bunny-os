#!/usr/bin/env python3
"""Generate bunhud's native sprite frames from Ava's Bun Bun artwork.

Takes the source GIFs (tools/bunhud/assets-src/), keys out the dark
studio background so she floats on anything, scales her to the overlay
size, and writes the frame PNGs bunhud cycles through. Run once per art
update; the device never needs PIL at runtime for the GIF work.

    scripts/gen_bunhud_frames.py
"""
from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "tools" / "bunhud" / "assets-src"
OUT = ROOT / "tools" / "bunhud" / "assets"

# The overlay draws her at half the art's native size: big enough to read
# on the Deck's screen, small enough to stay out of the game's way.
TARGET_W, TARGET_H = 170, 264

def key_background(img: Image.Image, bg: tuple[int, int, int], tol: int = 26) -> Image.Image:
    """Turn the flat studio background into transparency.

    Distance-based keying keeps anti-aliased edges soft instead of
    punching a hard hole; pixels closer to the key color than tol go
    fully transparent, with a soft ramp just past it.
    """
    img = img.convert("RGBA")
    px = img.load()
    w, h = img.size
    br, bgc, bb = bg
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            d = abs(r - br) + abs(g - bgc) + abs(b - bb)
            if d <= tol:
                px[x, y] = (r, g, b, 0)
            elif d <= tol * 3:
                px[x, y] = (r, g, b, min(255, int(255 * (d - tol) / (tol * 2))))
    # Shrink the fringe: blur the alpha once and re-threshold the extremes.
    alpha = img.split()[3].filter(ImageFilter.GaussianBlur(0.6))
    img.putalpha(alpha)
    return img

def cover_crop(img: Image.Image, w: int, h: int) -> Image.Image:
    """Scale to cover the box, then center-crop. Keeps her proportions."""
    sw, sh = img.size
    scale = max(w / sw, h / sh)
    img = img.resize((round(sw * scale), round(sh * scale)), Image.LANCZOS)
    left = (img.width - w) // 2
    top = (img.height - h) // 2
    return img.crop((left, top, left + w, top + h))

def frames_of(path: Path):
    im = Image.open(path)
    first = im.convert("RGB")
    bg = first.getpixel((2, 2))
    out = []
    i = 0
    while True:
        try:
            im.seek(i)
        except EOFError:
            break
        out.append(im.convert("RGB"))
        i += 1
    return out, bg

def main() -> int:
    idle_dir = OUT / "idle"
    idle_dir.mkdir(parents=True, exist_ok=True)
    for old in idle_dir.glob("*.png"):
        old.unlink()

    frames, bg = frames_of(SRC / "bunbun_moves_v2.gif")
    print(f"moves_v2: {len(frames)} frames, key {bg}")
    for i, fr in enumerate(frames):
        keyed = key_background(fr, bg)
        keyed = cover_crop(keyed, TARGET_W * 2, TARGET_H * 2)
        keyed = keyed.resize((TARGET_W, TARGET_H), Image.LANCZOS)
        keyed.save(idle_dir / f"f{i:02d}.png")
    print(f"wrote {len(frames)} idle frames -> {idle_dir}")

    wake_frames, wbg = frames_of(SRC / "bunbun_wake.gif")
    # The wake pose sits mid-sequence where the ears are fully up; frame 0
    # is the settled alert face. Use it as her listening sprite.
    keyed = key_background(wake_frames[0], wbg)
    keyed = cover_crop(keyed, TARGET_W * 2, TARGET_H * 2)
    keyed = keyed.resize((TARGET_W, TARGET_H), Image.LANCZOS)
    listen_path = OUT / "bunhud-listening.png"
    keyed.save(listen_path)
    print(f"wrote {listen_path}")

    # Contact sheet for the human eye: one strip, idle frames + listening.
    sheet = Image.new("RGBA", (TARGET_W * (len(frames) + 1) + 10 * (len(frames) + 1), TARGET_H), (40, 40, 60, 255))
    for i, p in enumerate(sorted(idle_dir.glob("f*.png"))):
        sheet.alpha_composite(Image.open(p), (i * (TARGET_W + 10), 0))
    sheet.alpha_composite(Image.open(listen_path), (len(frames) * (TARGET_W + 10), 0))
    sheet_path = OUT / "sheet-preview.png"
    sheet.save(sheet_path)
    print(f"wrote {sheet_path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
