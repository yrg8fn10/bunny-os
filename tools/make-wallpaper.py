"""Generate Bunny OS's desktop wallpaper.

No third-party libraries: a flat PNG writer is about twenty lines, and the
scene is soft gradients plus a few analytic shapes, which is exactly what
zlib compresses well. Keeping it generated means the artwork is reviewable in
a diff instead of being an opaque binary blob.

    python tools/make-wallpaper.py [out.png]

Scene: pastel sky, low sun, three rolling meadow hills, a pawprint trail and a
few flowers. 16:10 so it matches the Deck's 1280x800 panel without cropping.
"""
from __future__ import annotations

import math
import pathlib
import struct
import sys
import zlib

W, H = 1600, 1000
SCALE = W / 1280          # shapes are authored against a 1280-wide frame

OUT = pathlib.Path(__file__).resolve().parent.parent / \
    "iso/airootfs/usr/share/backgrounds/bunny-os/bunny-meadow.png"


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def mix(c1: tuple[float, float, float], c2: tuple[float, float, float],
        t: float) -> tuple[float, float, float]:
    t = max(0.0, min(1.0, t))
    return (lerp(c1[0], c2[0], t), lerp(c1[1], c2[1], t), lerp(c1[2], c2[2], t))


SKY_TOP = (0xCF, 0xE3, 0xFF)
SKY_MID = (0xFF, 0xE4, 0xF2)
SKY_LOW = (0xFF, 0xF1, 0xE6)

SUN = (0xFF, 0xF6, 0xDD)
SUN_POS = (1000.0, 190.0)
SUN_R = 92.0

HILLS = [
    # (base y, amplitude, wavelength, phase, colour)
    (300.0, 26.0, 240.0, 0.4, (0xD8, 0xF0, 0xEC)),
    (368.0, 34.0, 310.0, 1.6, (0xC2, 0xEA, 0xD8)),
    (452.0, 44.0, 390.0, 2.7, (0xA6, 0xDF, 0xC4)),
]

PAW = (0xFF, 0xF7, 0xFB)
FLOWER = (0xFF, 0xD6, 0xE8)


def hill_y(index: int, x: float) -> float:
    base, amp, wave, phase, _ = HILLS[index]
    # Two sines make the ridge look hand-drawn rather than like a sine wave.
    return (base
            + amp * math.sin(x * SCALE / wave + phase)
            + amp * 0.35 * math.sin(x * SCALE / (wave * 0.37) + phase * 2.1))


def in_ellipse(x: float, y: float, cx: float, cy: float,
               rx: float, ry: float) -> bool:
    dx = (x - cx) / rx
    dy = (y - cy) / ry
    return dx * dx + dy * dy <= 1.0


def stamp_paw(pix: bytearray, cx: float, cy: float, size: float,
              angle: float, colour: tuple[int, int, int], alpha: float) -> None:
    """One pawprint: a pad plus four toes, rotated as a group."""
    ca, sa = math.cos(angle), math.sin(angle)

    def place(dx: float, dy: float) -> tuple[float, float]:
        return (cx + dx * ca - dy * sa, cy + dx * sa + dy * ca)

    pad = (place(0, size * 0.18), size * 0.52, size * 0.40)
    toes = []
    for dx, dy in ((-0.44, -0.30), (-0.16, -0.52), (0.16, -0.52), (0.44, -0.30)):
        toes.append((place(dx * size, dy * size), size * 0.19, size * 0.17))

    x0 = max(0, int(cx - size * 1.6))
    x1 = min(W, int(cx + size * 1.6))
    y0 = max(0, int(cy - size * 1.6))
    y1 = min(H, int(cy + size * 1.6))

    for py in range(y0, y1):
        for px in range(x0, x1):
            hit = in_ellipse(px + 0.5, py + 0.5, pad[0][0], pad[0][1], pad[1], pad[2])
            if not hit:
                for (tx, ty), rx, ry in toes:
                    if in_ellipse(px + 0.5, py + 0.5, tx, ty, rx, ry):
                        hit = True
                        break
            if not hit:
                continue
            i = (py * W + px) * 3
            for k in range(3):
                pix[i + k] = int(pix[i + k] * (1 - alpha) + colour[k] * alpha)


def main(argv: list[str]) -> int:
    out = pathlib.Path(argv[1]) if len(argv) > 1 else OUT
    pix = bytearray(W * H * 3)

    # --- sky + hills, one pass -------------------------------------------
    for y in range(H):
        fy = y / H
        if fy < 0.62:
            sky = mix(SKY_TOP, SKY_MID, fy / 0.62)
        else:
            sky = mix(SKY_MID, SKY_LOW, (fy - 0.62) / 0.38)

        # Glow around the sun, computed once per row distance is not separable,
        # so it is applied per pixel below only inside a bounding box.
        row = y * W * 3
        for x in range(W):
            i = row + x * 3
            pix[i] = int(sky[0])
            pix[i + 1] = int(sky[1])
            pix[i + 2] = int(sky[2])

    # sun + glow
    x0, x1 = int(SUN_POS[0] - SUN_R * 4), int(SUN_POS[0] + SUN_R * 4)
    y0, y1 = int(SUN_POS[1] - SUN_R * 4), int(SUN_POS[1] + SUN_R * 4)
    for py in range(max(0, y0), min(H, y1)):
        for px in range(max(0, x0), min(W, x1)):
            d = math.hypot(px - SUN_POS[0], py - SUN_POS[1])
            if d > SUN_R * 3.4:
                continue
            alpha = 0.0
            if d <= SUN_R:
                alpha = 0.95
            elif d < SUN_R * 3.4:
                alpha = 0.55 * (1 - (d - SUN_R) / (SUN_R * 2.4)) ** 2
            if alpha <= 0:
                continue
            i = (py * W + px) * 3
            for k in range(3):
                pix[i + k] = int(pix[i + k] * (1 - alpha) + SUN[k] * alpha)

    # soft clouds
    clouds = [
        (300, 170, 120, 34, 0.55), (430, 150, 90, 26, 0.45),
        (760, 250, 150, 30, 0.40), (1180, 320, 110, 24, 0.35),
    ]
    for cx, cy, rx, ry, a in clouds:
        for py in range(max(0, int(cy - ry)), min(H, int(cy + ry))):
            for px in range(max(0, int(cx - rx)), min(W, int(cx + rx))):
                t = 1 - ((px - cx) / rx) ** 2 - ((py - cy) / ry) ** 2
                if t <= 0:
                    continue
                alpha = a * min(1.0, t * 1.6)
                i = (py * W + px) * 3
                for k in range(3):
                    pix[i + k] = int(pix[i + k] * (1 - alpha) + 255 * alpha)

    # hills, far to near
    for index in range(len(HILLS)):
        _, _, _, _, colour = HILLS[index]
        tint = min(1.0, 0.06 * index)
        for x in range(W):
            ridge = hill_y(index, x)
            start = max(0, int(ridge))
            for py in range(start, H):
                depth = (py - ridge) / max(1.0, H - ridge)
                shade = mix(colour, (colour[0] * 0.94, colour[1] * 0.97, colour[2] * 0.96),
                            depth * 0.8 + tint * 0.2)
                i = (py * W + x) * 3
                pix[i] = int(shade[0])
                pix[i + 1] = int(shade[1])
                pix[i + 2] = int(shade[2])

    # pawprint trail along the near hill
    trail = [
        (250, 640, 30, -0.35), (330, 690, 32, -0.30), (410, 745, 34, -0.25),
        (500, 800, 36, -0.18), (600, 852, 38, -0.10), (710, 898, 40, -0.02),
        (830, 936, 42, 0.06),
    ]
    for cx, cy, size, angle in trail:
        # alternate left/right paws around the trail centre line
        side = -1 if trail.index((cx, cy, size, angle)) % 2 == 0 else 1
        stamp_paw(pix, cx * SCALE, cy + side * 22, size * SCALE, angle, PAW, 0.42)

    # a few flowers on the near hill
    for fx, fy in ((180, 780), (300, 900), (980, 840), (1120, 760),
                   (1240, 900), (760, 960), (1420, 830)):
        cx, cy = fx * SCALE, fy
        for py in range(int(cy - 9), int(cy + 9)):
            for px in range(int(cx - 9), int(cx + 9)):
                if (px - cx) ** 2 + (py - cy) ** 2 > 64:
                    continue
                i = (py * W + px) * 3
                for k in range(3):
                    pix[i + k] = int(pix[i + k] * 0.55 + FLOWER[k] * 0.45)

    # --- PNG --------------------------------------------------------------
    raw = b"".join(b"\x00" + bytes(pix[y * W * 3:(y + 1) * W * 3]) for y in range(H))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 9))
           + chunk(b"IEND", b""))

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(png)
    print(f"wrote {out} ({len(png)} bytes, {W}x{H})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
