"""Qwen3-TTS backend (Bun Bun's official voice) tests.

The engine itself is never run here; the tests pin the command shape, the
mood-to-instruct mapping and the detection order, with a fake binary.
"""
from __future__ import annotations

import subprocess
import sys
import types
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bunbun.tts.backends as tts_backends  # noqa: E402
from bunbun.tts.backends import QwenTTSBackend, detect  # noqa: E402


def _make(tmp_path: Path, binary_exists: bool = True) -> QwenTTSBackend:
    talker = tmp_path / "talker.gguf"
    talker.write_bytes(b"gguf")
    codec = tmp_path / "codec.gguf"
    codec.write_bytes(b"gguf")
    binary = tmp_path / "bunbun-qwen-tts"
    if binary_exists:
        binary.write_text("#!/bin/sh\n")
        binary.chmod(0o755)
    return QwenTTSBackend(binary=str(binary), model=talker, codec=codec)


def _config(**kw):
    base = dict(tts_backend="auto", voice_bank=None, piper_model=None,
                voice="bunny-default", voice_speaker=None)
    base.update(kw)
    return types.SimpleNamespace(**base)


def _env_qwentts(monkeypatch, tmp_path) -> None:
    binary = tmp_path / "bunbun-qwen-tts"
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o755)
    talker = tmp_path / "talker.gguf"
    talker.write_bytes(b"gguf")
    codec = tmp_path / "codec.gguf"
    codec.write_bytes(b"gguf")
    monkeypatch.setenv("BUNBUN_QWENTTS_BIN", str(binary))
    monkeypatch.setenv("BUNBUN_QWENTTS_TALKER", str(talker))
    monkeypatch.setenv("BUNBUN_QWENTTS_CODEC", str(codec))


def test_available_true_with_binary_and_models(tmp_path):
    assert _make(tmp_path).available() is True


def test_unavailable_without_binary(tmp_path):
    assert _make(tmp_path, binary_exists=False).available() is False


def test_unavailable_without_models(tmp_path):
    backend = _make(tmp_path)
    backend.model = tmp_path / "missing.gguf"
    assert backend.available() is False


def test_synthesize_builds_the_proven_command(tmp_path):
    backend = _make(tmp_path)
    out = tmp_path / "line.wav"
    recorded = {}

    def fake_run(cmd, input=None, capture_output=None, timeout=None, check=None):
        recorded["cmd"] = cmd
        recorded["stdin"] = input
        out.write_bytes(b"RIFFfake")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    with mock.patch("bunbun.tts.backends.subprocess.run", side_effect=fake_run):
        assert backend.synthesize("Hello, I'm Bun Bun!", out) is True

    cmd = recorded["cmd"]
    assert cmd[0].endswith("bunbun-qwen-tts")
    assert cmd[cmd.index("--speaker") + 1] == "serena"
    assert cmd[cmd.index("--lang") + 1] == "English"
    assert cmd[cmd.index("--instruct") + 1] == QwenTTSBackend.INSTRUCT_DEFAULT
    assert cmd[cmd.index("--max-new") + 1] == "150"
    assert cmd[cmd.index("--codec-chunk-dur") + 1] == "4.0"
    assert cmd[cmd.index("-o") + 1] == str(out)
    assert recorded["stdin"] == b"Hello, I'm Bun Bun!"


def test_synthesize_reports_engine_failure(tmp_path):
    backend = _make(tmp_path)
    with mock.patch("bunbun.tts.backends.subprocess.run",
                           return_value=subprocess.CompletedProcess([], 1, b"", b"")):
        assert backend.synthesize("hi", tmp_path / "line.wav") is False


def test_mood_maps_to_approved_instructs(tmp_path):
    backend = _make(tmp_path)
    backend.set_params(length_scale=0.9, noise_scale=0.6)
    assert backend.instruct == QwenTTSBackend.INSTRUCT_DEFAULT
    backend.set_params(length_scale=1.2, noise_scale=0.6)  # bedtime-soft
    assert backend.instruct == QwenTTSBackend.INSTRUCT_SLOW
    backend.set_params(length_scale=1.0, noise_scale=0.85)  # rough night
    assert backend.instruct == QwenTTSBackend.INSTRUCT_ENCOURAGING


def test_detect_auto_puts_qwentts_first(monkeypatch, tmp_path):
    _env_qwentts(monkeypatch, tmp_path)
    chain = detect(_config(tts_backend="auto"))
    backends = getattr(chain, "backends", None) or [chain]
    assert backends[0].name == "qwentts"


def test_detect_explicit_qwentts_is_qwentts_alone(monkeypatch, tmp_path):
    _env_qwentts(monkeypatch, tmp_path)
    backend = detect(_config(tts_backend="qwentts"))
    assert backend.name == "qwentts"
    assert not hasattr(backend, "backends")


def test_env_override_missing_files_means_unavailable(monkeypatch, tmp_path):
    binary = tmp_path / "bunbun-qwen-tts"
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o755)
    monkeypatch.setenv("BUNBUN_QWENTTS_BIN", str(binary))
    monkeypatch.setenv("BUNBUN_QWENTTS_TALKER", str(tmp_path / "nope.gguf"))
    monkeypatch.setenv("BUNBUN_QWENTTS_CODEC", str(tmp_path / "also-nope.gguf"))
    backend = QwenTTSBackend(binary=str(binary), model=None, codec=None)
    assert backend.model is None and backend.codec is None
    assert backend.available() is False
