#!/usr/bin/env python3
"""Procedurally draws the placeholder bunhud sprite (no 3D, no asset files).

This is a stand-in until real Bun Bun art is chosen: a simple chibi
bunny head with pink ears and a cyan glow, on a transparent background.
Swap in real art any time with --sprite.
"""
from PIL import Image, ImageDraw

W, H = 128, 160
img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

PINK = (255, 140, 200, 255)
PINK_DARK = (214, 84, 158, 255)
WHITE = (255, 250, 252, 255)
CYAN = (0, 229, 255, 255)
OUTLINE = (60, 20, 50, 255)

# ears (two long rounded rectangles)
for x0 in (28, 70):
    d.ellipse([x0, 2, x0 + 30, 78], fill=PINK, outline=OUTLINE, width=3)
    d.ellipse([x0 + 8, 14, x0 + 22, 66], fill=PINK_DARK)
# head
d.ellipse([8, 58, 120, 148], fill=WHITE, outline=OUTLINE, width=3)
# eyes
d.ellipse([38, 92, 54, 108], fill=OUTLINE)
d.ellipse([74, 92, 90, 108], fill=OUTLINE)
# cyan sparkle pupils
d.ellipse([44, 96, 50, 102], fill=CYAN)
d.ellipse([80, 96, 86, 102], fill=CYAN)
# nose + smile
d.ellipse([59, 112, 69, 120], fill=PINK_DARK)
d.arc([52, 112, 76, 132], start=20, end=160, fill=OUTLINE, width=3)
# soft cyan glow ring behind (drawn first would be under; add as accent)
img.save("assets/bunhud-placeholder.png")
print("wrote assets/bunhud-placeholder.png")
