"""Unit checks for bunhud's MAM bridge (no service or Wayland needed)."""
import importlib.util
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "mam_bridge", _TOOLS / "mam_bridge.py"
)
mam_bridge = importlib.util.module_from_spec(spec)
sys.modules["mam_bridge"] = mam_bridge
spec.loader.exec_module(mam_bridge)


def test_parse_sse_line():
    assert mam_bridge.parse_sse_line(
        'data: {"topic":"game.started","payload":{},"ts":1}'
    ) == {"topic": "game.started", "payload": {}, "ts": 1}
    assert mam_bridge.parse_sse_line(": keepalive") is None
    assert mam_bridge.parse_sse_line("data: not-json") is None


def test_event_to_command():
    assert mam_bridge.event_to_command({"topic": "game.started"}) == {
        "cmd": "show", "text": None,
    }
    spoken = {"topic": "bunbun.spoken", "payload": {"text": "hop hop!"}}
    assert mam_bridge.event_to_command(spoken) == {
        "cmd": "speak", "text": "hop hop!",
    }
    # No text in the payload: still speak, just with nothing to draw.
    assert mam_bridge.event_to_command(
        {"topic": "bunbun.spoken", "payload": {}}
    ) == {"cmd": "speak", "text": None}
    assert mam_bridge.event_to_command({"topic": "agent.started"}) == {
        "cmd": "show", "text": None,
    }
    assert mam_bridge.event_to_command({"topic": "player.spoke"}) == {
        "cmd": "listen", "text": None,
    }
    assert mam_bridge.event_to_command({"topic": "agent.stopped"}) == {
        "cmd": "hide", "text": None,
    }
    assert mam_bridge.event_to_command({"topic": "bunbun.error"}) is None
    assert mam_bridge.event_to_command(None) is None
    assert mam_bridge.event_to_command("junk") is None
