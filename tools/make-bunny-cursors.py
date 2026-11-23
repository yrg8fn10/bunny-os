#!/usr/bin/env python3
"""Build the BunnyCursor X cursor theme (Bun Bun's pink-glow set).

Draws every cursor frame at high resolution with Pillow, then packs the
frames into Xcursor binaries so the theme works on X11 and Wayland (Plasma
reads the same files on both). Fully local, no network, no third-party art.

Usage: python3 tools/make-bunny-cursors.py [OUTDIR]
"""
import math
import os
import struct
import sys

from PIL import Image, ImageDraw, ImageFilter

PINK = (255, 156, 199, 255)
PINK_SOFT = (255, 179, 217, 255)
WHITE = (255, 252, 250, 255)
INK = (96, 74, 88, 255)
BLUSH = (255, 191, 214, 160)
CARROT = (245, 138, 60, 255)
GLOW = (255, 156, 199, 170)

OUT = sys.argv[1] if len(sys.argv) > 1 else "out/cursor-preview"
S = 8           # supersample factor
BASE = 64       # design space is 64x64 units
CANVAS = BASE * S


def s(v):
    return int(round(v * S))


# --- low-level drawing helpers ----------------------------------------------

def shape_layers(draws, canvas_img):
    """Draw a union of shapes with one clean outline: pass 1 fills every
    shape in the outline colour (padded by the outline width), pass 2 fills
    them in the body colour on top, so interior seams never show."""
    d = ImageDraw.Draw(canvas_img)
    w = s(2.2)
    for fn in draws:
        fn(d, fill=PINK, outline=PINK, width=w * 2)
    for fn in draws:
        fn(d, fill=WHITE, outline=None, width=0)


def ell(draw, box, **kw):
    draw.ellipse([s(c) for c in box], **kw)


def rr(draw, box, radius, **kw):
    kw2 = dict(kw)
    if "width" in kw2 and kw2["width"]:
        kw2["width"] = int(kw2["width"])
    draw.rounded_rectangle([s(c) for c in box], radius=s(radius), **kw2)


def polyg(draw, pts, **kw):
    flat = [s(c) for p in pts for c in p]
    kw2 = dict(kw)
    if "width" in kw2 and kw2["width"]:
        kw2["width"] = int(kw2["width"])
    draw.polygon(flat, **kw2)


def ear_layer(length=13.0, width=5.0):
    """One vertical ear capsule, white with pink outline and pink inner."""
    W = int(length * S) + 4 * s(2.2)
    H = int(width * 2 * S) + 4 * s(2.2)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    w = s(2.2)
    box = [2 * s(2.2), 2 * s(2.2), 2 * s(2.2) + int(length * S), 2 * s(2.2) + int(width * 2 * S)]
    d.rounded_rectangle(box, radius=box[3] // 2, fill=PINK, outline=PINK, width=w * 2)
    ib = [box[0] + int(length * S * 0.30), box[1] + int(width * 2 * S * 0.18),
          box[0] + int(length * S * 0.92), box[3] - int(width * 2 * S * 0.18)]
    d.rounded_rectangle(ib, radius=(ib[3] - ib[1]) // 2, fill=PINK_SOFT)
    return img


def paste_ear(canvas_img, base_xy, angle_deg, length=13.0, width=5.0):
    """Pastes an ear so its BASE sits at base_xy (design units), tilted angle_deg."""
    img = ear_layer(length, width).rotate(angle_deg, expand=True, resample=Image.BICUBIC)
    L = length * S
    bx, by = s(base_xy[0]), s(base_xy[1])
    rad = math.radians(angle_deg)
    # base point sits at 2.2*2 inset from the capsule bottom-left before rotation
    ax, ay = 2 * s(2.2) + L / 2, 2 * s(2.2)
    # rotate that anchor point
    cx, cy = img.width / 2, img.height / 2
    ox, oy = ax - cx, ay - cy
    rx = ox * math.cos(rad) + oy * math.sin(rad)
    ry = -ox * math.sin(rad) + oy * math.cos(rad)
    px = int(bx - (rx + cx))
    py = int(by - (ry + cy))
    canvas_img.alpha_composite(img, (px, py))


def face(d, cx, cy, sc=1.0):
    ex = 3.2 * sc
    for sx in (-1, 1):
        ell(d, (cx + sx * ex - 1.0 * sc, cy - 0.8 * sc, cx + sx * ex + 1.0 * sc, cy + 1.2 * sc), fill=INK)
        ell(d, (cx + sx * ex - 2.6 * sc, cy + 1.4 * sc, cx + sx * ex + 0.2 * sc, cy + 3.0 * sc), fill=BLUSH)
    d.arc([s(cx - 1.6 * sc), s(cy + 1.8 * sc), s(cx + 1.6 * sc), s(cy + 4.2 * sc)], 200, 340,
          fill=INK, width=max(1, s(0.7)))


def paw(d, cx, cy, r, rot=0.0):
    for ang, (dx, dy, rr_) in zip((0, 120, 240), ((0, -0.95, 0.40), (-0.62, -0.55, 0.34), (0.62, -0.55, 0.34))):
        a = math.radians(ang + rot)
        x = cx + (dx * math.cos(a) - dy * math.sin(a)) * r
        y = cy + (dx * math.sin(a) + dy * math.cos(a)) * r
        ell(d, (x - rr_ * r, y - rr_ * r, x + rr_ * r, y + rr_ * r), fill=PINK)
    ell(d, (cx - 0.66 * r, cy - 0.5 * r, cx + 0.66 * r, cy + 0.66 * r), fill=PINK)


def glow_and_finish(img, size):
    a = img.split()[3].filter(ImageFilter.GaussianBlur(2.2 * S / 2))
    g = Image.new("RGBA", img.size, GLOW)
    g.putalpha(a)
    img = Image.alpha_composite(g, img)
    return img.resize((size, size), Image.LANCZOS)


def render(size, painter):
    """painter draws on a fresh 64-space canvas; returns the finished size px image."""
    img = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    painter(img)
    return glow_and_finish(img, size)


# --- cursor painters ---------------------------------------------------------

ARROW = [(18, 10), (18, 46), (27, 38.5), (34, 54), (42, 50.5), (35, 36), (47, 35)]


def arrow_painter(img):
    def base(d, **kw):
        polyg(d, ARROW, **kw)
    paste_ear(img, (15.0, 12.5), 24)
    paste_ear(img, (21.0, 12.5), -24)
    shape_layers([base], img)


def hand_painter(img):
    def palm(d, **kw):
        ell(d, (20, 30, 46, 52), **kw)

    def index(d, **kw):
        rr(d, (27, 10, 36, 38), 4.4, **kw)

    def thumb(d, **kw):
        ell(d, (16, 34, 27, 44), **kw)

    shape_layers([palm, index, thumb], img)
    d = ImageDraw.Draw(img)
    ell(d, (29.5, 12, 33.5, 16), fill=PINK_SOFT)
    face(d, 33, 40, sc=0.75)


def ibeam_painter(img):
    def bar(d, **kw):
        rr(d, (29, 14, 35, 50), 3, **kw)

    def top(d, **kw):
        polyg(d, [(29, 16), (35, 16), (32, 9)], **kw)

    def bot(d, **kw):
        polyg(d, [(29, 48), (35, 48), (32, 55)], **kw)

    shape_layers([bar, top, bot], img)
    d = ImageDraw.Draw(img)
    for tri in ([(29, 16), (35, 16), (32, 9)], [(29, 48), (35, 48), (32, 55)]):
        polyg(d, tri, fill=CARROT)


def spinner_painter(i, total=8):
    def paint(img):
        d = ImageDraw.Draw(img)
        cx, cy = 32, 36
        ell(d, (cx - 13, cy - 10, cx + 13, cy + 14), fill=WHITE, outline=PINK, width=s(2.2))
        ears_tilt = 7 * (1 if i % 2 else -1)
        paste_ear(img, (cx - 4.6, cy - 8.5), 10 + ears_tilt, length=11, width=4.2)
        paste_ear(img, (cx + 4.6, cy - 8.5), -10 - ears_tilt, length=11, width=4.2)
        face(d, cx, cy + 2, sc=0.95)
        dd = ImageDraw.Draw(img)
        for k in range(6):
            a = math.radians(k * 60 + i * (360 / total))
            paw(dd, cx + 22 * math.cos(a), cy + 2 + 22 * math.sin(a), 3.2)
    return paint


# --- Xcursor packing ---------------------------------------------------------

IMAGE_TYPE = 0xFFFD0002


def write_xcursor(path, entries):
    toc, blobs = [], []
    pos = 16 + 12 * sum(len(v) for v in entries.values())
    for nominal in sorted(entries):
        for (w, h, xh, yh, delay, px) in entries[nominal]:
            toc.append((IMAGE_TYPE, nominal, pos))
            chunk = struct.pack("<9I", 36, IMAGE_TYPE, nominal, 1 << 16, w, h, xh, yh, delay)
            blobs.append(chunk + px)
            pos += len(chunk) + len(px)
    out = bytearray()
    out += struct.pack("<4sIII", b"Xcur", 16, 1 << 16, len(toc))
    for (t, sub, p) in toc:
        out += struct.pack("<III", t, sub, p)
    for b in blobs:
        out += b
    data = bytes(out)
    with open(path, "wb") as f:
        f.write(data)
    return data


def verify_xcursor(data):
    magic, header, version, ntoc = struct.unpack_from("<4sIII", data, 0)
    assert magic == b"Xcur" and header == 16 and ntoc >= 1, "bad xcursor header"
    offset = header
    for _ in range(ntoc):
        t, sub, pos = struct.unpack_from("<III", data, offset)
        offset += 12
        assert pos + 36 <= len(data), "toc beyond file"
        h, t2, sub2, ver, w, hgt, xh, yh, delay = struct.unpack_from("<9I", data, pos)
        assert t2 == IMAGE_TYPE, "toc type mismatch"
        assert len(data) >= pos + 36 + w * hgt * 4, "image truncated"


def pack(name, frames_by_size):
    entries = {}
    for size, frames in frames_by_size.items():
        lst = []
        for (img, xh, yh, delay) in frames:
            px = img.tobytes()
            argb = bytearray(len(px))
            argb[0::4] = px[2::4]
            argb[1::4] = px[1::4]
            argb[2::4] = px[0::4]
            argb[3::4] = px[3::4]
            lst.append((img.width, img.height, xh, yh, delay, bytes(argb)))
        entries[size] = lst
    data = write_xcursor(os.path.join(OUT, "cursors", name), entries)
    verify_xcursor(data)


SIZES = (24, 32, 48)
SCALE_MAP = {24: 0.72, 32: 0.86, 48: 1.0}


def build_static(name, painter, hot, hot_y):
    by = {}
    for size in SIZES:
        img = render(size, painter)
        k = SCALE_MAP[size]
        by[size] = [(img, int(hot * k), int(hot_y * k), 50)]
    pack(name, by)


def build_anim(name, frames=8, delay_ms=90):
    by = {}
    for size in SIZES:
        lst = []
        for i in range(frames):
            lst.append((render(size, spinner_painter(i)), s(32) * size // CANVAS, s(38) * size // CANVAS, delay_ms))
        by[size] = lst
    pack(name, by)


def main():
    os.makedirs(os.path.join(OUT, "cursors"), exist_ok=True)
    build_static("left_ptr", arrow_painter, 18, 10)
    build_static("pointing_hand", hand_painter, 31.5, 10)
    build_static("ibeam", ibeam_painter, 32, 10)
    build_anim("wait")
    curs = os.path.join(OUT, "cursors")
    for alias, target in [("hand2", "pointing_hand"), ("xterm", "ibeam"),
                          ("watch", "wait"), ("busy", "wait"),
                          ("progress", "wait"), ("left_ptr_watch", "wait")]:
        p = os.path.join(curs, alias)
        if os.path.lexists(p):
            os.remove(p)
        os.symlink(target, p)
    with open(os.path.join(OUT, "index.theme"), "w") as f:
        f.write("[Icon Theme]\nName=BunnyCursor\n"
                "Comment=Bun Bun's pink-glow cursor set for Bunny OS\n"
                "Inherits=breeze_cursors\n")
    # preview sheet on light and dark
    sheet = Image.new("RGBA", (660, 300), (58, 60, 66, 255))
    x = 24
    for name, painter in (("left_ptr", arrow_painter), ("pointing_hand", hand_painter), ("ibeam", ibeam_painter)):
        img = render(72, painter)
        sheet.alpha_composite(img, (x, 30))
        sheet.alpha_composite(img, (x, 140))
        x += 92
    for i in (0, 2, 4):
        img = render(72, spinner_painter(i))
        sheet.alpha_composite(img, (x, 30))
        x += 92
    light = Image.new("RGBA", (660, 300), (238, 234, 240, 255))
    light.alpha_composite(sheet)
    sheet.save(os.path.join(OUT, "preview.png"))
    light.convert("RGB").save(os.path.join(OUT, "preview-light.png"))
    print("wrote theme to", OUT)


if __name__ == "__main__":
    main()
