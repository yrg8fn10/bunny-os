"""Unit check for bunhud's sprite-to-ARGB conversion (runs without Wayland)."""
import importlib.util
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("bunhud", _TOOLS / "bunhud.py")
bunhud = importlib.util.module_from_spec(spec)
sys.modules["bunhud"] = bunhud
spec.loader.exec_module(bunhud)


def test_sprite_to_argb():
    from PIL import Image

    img = Image.new("RGBA", (4, 2), (255, 0, 0, 255))
    data, w, h = bunhud.sprite_to_argb(img)
    assert (w, h) == (4, 2)
    assert len(data) == w * h * 4
    # first pixel: opaque red -> premultiplied B,G,R,A
    assert data[0:4] == bytes((0, 0, 255, 255))
    # transparent pixel stays zeroed
    img2 = Image.new("RGBA", (1, 1), (255, 255, 255, 0))
    data2, _, _ = bunhud.sprite_to_argb(img2)
    assert data2 == b"\x00\x00\x00\x00"
    # half-alpha white: premultiplied channels halve
    img3 = Image.new("RGBA", (1, 1), (255, 255, 255, 128))
    data3, _, _ = bunhud.sprite_to_argb(img3)
    assert data3 == bytes((128, 128, 128, 128))
