#!/usr/bin/env python3
"""Bunny OS repository verification — no Arch, no root, no network required.

This is the check you can run anywhere (including Windows) before spending 40
minutes on an ISO build.  It validates structure, JSON, unit/desktop headers,
line endings, template tokens and the safety invariants that are easy to break.

    python3 tools/verify.py            # human readable
    python3 tools/verify.py --json     # machine readable
    python3 tools/verify.py --strict   # treat warnings as failures
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REQUIRED = [
    "VERSION",
    "build_bunny_os_iso.sh",
    "iso/profiledef.sh",
    "iso/packages.x86_64",
    "iso/pacman.conf",
    "iso/airootfs/root/customize_airootfs.sh",
    "iso/airootfs/etc/os-release",
    "iso/airootfs/etc/bunny/settings.json",
    "iso/airootfs/etc/sddm.conf.d/10-bunny.conf",
    "iso/airootfs/etc/sddm.conf.d/20-bunny-session.conf",
    "system/bin/bunny-session",
    "system/bin/bunny-panel",
    "system/bin/bunny-panel-bridge",
    "system/bin/bunnyctl",
    "system/bin/bunny-firstboot",
    "system/bin/bunny-update",
    "system/bin/bunny-health",
    "system/lib/bunny_sessiond.py",
    "system/lib/bunny_input_agent.py",
    "system/units/bunny-sessiond.service",
    "system/units/bunny-firstboot.service",
    "system/units/bunny-update.service",
    "system/units/bunny-update.timer",
    "system/units/bunny-health.service",
    "system/units/bunny-health.timer",
    "system/units/bunny-input-agent.service",
    "system/user-units/bunny-bunbun.service",
    "system/wayland-sessions/bunny-gaming.desktop",
    "system/wayland-sessions/bunny-desktop.desktop",
    "bunbun/pyproject.toml",
    "bunbun/bunbun/service.py",
    "bunbun/bunbun/mam/policy.py",
    "bunbun/bunbun/mam/engine.py",
    "bunbun/bunbun/data/persona.json",
    "bunbun/tests/test_policy.py",
    "bunbun/tests/test_engine.py",
    "bunbun/tests/test_service.py",
    "control-panel/ui/index.html",
    "control-panel/ui/js/app.js",
    "control-panel/ui/css/panel.css",
    "control-panel/ui/assets/bunny.svg",
    "control-panel/src-tauri/Cargo.toml",
    "control-panel/src-tauri/tauri.conf.json",
    "launchers/bin/bunny-launcher",
    "launchers/bin/bunny-platform-scan",
    "installer/bunny-install",
    "iso/targets/deck/target.conf",
    "iso/targets/deck/packages.x86_64",
    "iso/targets/deck/overlay/efiboot/loader/entries/01-bunny-os.conf",
    "iso/targets/deck/airootfs/etc/systemd/zram-generator.conf",
    "docs/ARCHITECTURE.md",
    "docs/BUILD.md",
    "docs/SESSIONS.md",
    "docs/BUNBUN.md",
    "docs/SAFETY-AND-LEGAL.md",
    "docs/STEAMDECK.md",
    ".github/workflows/build-iso.yml",
]

TEXT_SUFFIXES = {".sh", ".py", ".js", ".css", ".html", ".json", ".md",
                 ".service", ".timer", ".desktop", ".conf", ".toml"}
SKIP_DIRS = {"build", "out", "node_modules", "target", ".git", "__pycache__", "vendor"}
EXTRA_TEXT_NAMES = {"bunnyctl", "bunny-session", "bunny-panel", "bunny-panel-bridge",
                    "bunny-firstboot", "bunny-update", "bunny-health", "bunny-launcher",
                    "bunny-platform-scan", "bunny-install", "bunny-cli", "Makefile",
                    "VERSION", ".gitignore", ".editorconfig"}

SECRET_RE = re.compile(r"(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})")
TOKEN_RE = re.compile(r"@[A-Z][A-Z0-9_]{2,}@")
FORBIDDEN_PKGS = {"heroic-games-launcher", "heroic-games-launcher-bin", "yay", "paru",
                  "google-chrome", "visual-studio-code-bin", "spotify"}


class Report:
    def __init__(self, strict: bool = False):
        self.strict = strict
        self.checks: list[dict] = []

    def add(self, ok: bool, name: str, detail: str = "", warn: bool = False) -> None:
        status = "pass" if ok else ("warn" if warn and not self.strict else "fail")
        self.checks.append({"name": name, "status": status, "detail": detail})
        icon = {"pass": "\033[32m✓\033[0m", "warn": "\033[33m!\033[0m",
                "fail": "\033[31m✗\033[0m"}[status]
        line = f"  {icon} {name}"
        if detail and status != "pass":
            line += f"  ({detail})"
        print(line)

    @property
    def failures(self) -> list[dict]:
        return [c for c in self.checks if c["status"] == "fail"]

    @property
    def warnings(self) -> list[dict]:
        return [c for c in self.checks if c["status"] == "warn"]


def walk(suffixes: set[str] | None = None):
    for path in ROOT.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue
        if suffixes is None or path.suffix in suffixes:
            yield path


def iter_text_files():
    """Every file that should contain LF text (scripts without suffixes too)."""
    for path in walk():
        if path.suffix in TEXT_SUFFIXES or path.name in EXTRA_TEXT_NAMES:
            yield path


def check_required(rep: Report) -> None:
    print("\nstructure")
    missing = [rel for rel in REQUIRED if not (ROOT / rel).is_file()]
    rep.add(not missing, f"{len(REQUIRED) - len(missing)}/{len(REQUIRED)} required files present",
            ", ".join(missing[:6]))
    empty = [rel for rel in REQUIRED if (ROOT / rel).is_file()
             and (ROOT / rel).stat().st_size == 0]
    rep.add(not empty, "no empty required files", ", ".join(empty[:6]))


def check_json(rep: Report) -> None:
    print("\njson")
    bad = []
    for path in walk({".json"}):
        try:
            json.loads(path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            bad.append(f"{path.relative_to(ROOT)}: {exc}")
    rep.add(not bad, "all JSON parses", "; ".join(bad[:3]))


def check_units(rep: Report) -> None:
    print("\nsystemd")
    units = list(walk({".service", ".timer"}))
    bad = []
    for unit in units:
        text = unit.read_text("utf-8", errors="replace")
        if "[Unit]" not in text:
            bad.append(f"{unit.name}: no [Unit]")
        if unit.suffix == ".service" and "[Service]" not in text:
            bad.append(f"{unit.name}: no [Service]")
        if unit.suffix == ".timer" and "[Timer]" not in text:
            bad.append(f"{unit.name}: no [Timer]")
        if unit.suffix == ".service" and "ExecStart" not in text:
            bad.append(f"{unit.name}: no ExecStart")
    rep.add(not bad, f"{len(units)} units structurally valid", "; ".join(bad[:3]))

    # The session daemon must be root-only; Bun Bun must be a user unit.
    sessiond = (ROOT / "system/units/bunny-sessiond.service").read_text("utf-8")
    rep.add("User=" not in sessiond, "bunny-sessiond runs as root (no User= drop)")
    bunbun_unit = ROOT / "system/user-units/bunny-bunbun.service"
    rep.add(bunbun_unit.is_file(), "Bun Bun ships as a user unit")
    input_unit = (ROOT / "system/units/bunny-input-agent.service").read_text("utf-8")
    rep.add("ConditionPathExists=/etc/bunny/allow-input-agent" in input_unit,
            "input agent requires the consent token")


def check_desktop(rep: Report) -> None:
    print("\ndesktop entries")
    entries = list(walk({".desktop"}))
    bad = []
    for entry in entries:
        text = entry.read_text("utf-8", errors="replace")
        for key in ("[Desktop Entry]", "Name=", "Type=", "Exec="):
            if key not in text:
                bad.append(f"{entry.name}: missing {key}")
    rep.add(not bad, f"{len(entries)} desktop entries valid", "; ".join(bad[:3]))


def check_line_endings(rep: Report) -> None:
    print("\nhygiene")
    crlf = [str(p.relative_to(ROOT)) for p in iter_text_files()
            if b"\r\n" in p.read_bytes()]
    rep.add(not crlf, "no CRLF line endings", ", ".join(crlf[:5]))

    secrets = []
    for path in iter_text_files():
        try:
            if SECRET_RE.search(path.read_text("utf-8", errors="ignore")):
                secrets.append(str(path.relative_to(ROOT)))
        except OSError:
            continue
    rep.add(not secrets, "no hardcoded API keys", ", ".join(secrets[:3]))

    # Unrendered template tokens must only exist in files that get rendered.
    allowed_tokens = {
        "iso/profiledef.sh", "iso/airootfs/etc/os-release", "iso/airootfs/etc/motd",
        "iso/overrides/efiboot/loader/entries/01-bunny-os.conf",
        "iso/overrides/syslinux/syslinux.cfg",
        "iso/targets/deck/overlay/efiboot/loader/entries/01-bunny-os.conf",
        "tools/verify.py",
    }
    stray = []
    for path in iter_text_files():
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        if rel in allowed_tokens or rel.startswith("docs/") or rel.endswith("README.md"):
            continue
        for match in TOKEN_RE.finditer(path.read_text("utf-8", errors="ignore")):
            if match.group(0) in {"@VERSION@", "@BUILD_ID@", "@BUILD_DATE@", "@CHANNEL@"}:
                stray.append(f"{rel}:{match.group(0)}")
    rep.add(not stray, "template tokens confined to rendered files", ", ".join(stray[:5]))


def check_packages(rep: Report) -> None:
    print("\narchiso profile")
    pkg_file = ROOT / "iso/packages.x86_64"
    packages = [ln.strip() for ln in pkg_file.read_text("utf-8").splitlines()
                if ln.strip() and not ln.lstrip().startswith("#")]
    bad = [p for p in packages if p in FORBIDDEN_PKGS]
    rep.add(not bad, "no AUR-only packages", ", ".join(bad))
    invalid = [p for p in packages if not re.fullmatch(r"[a-z0-9@._+-]+", p)]
    rep.add(not invalid, f"{len(packages)} package names well formed", ", ".join(invalid[:5]))
    rep.add("multilib" in (ROOT / "iso/pacman.conf").read_text("utf-8"),
            "multilib repository enabled (Steam 32-bit libs)")

    profile = (ROOT / "iso/profiledef.sh").read_text("utf-8")
    for key in ("iso_name=", "iso_label=", "bootmodes=", "install_dir=", "airootfs_image_type="):
        rep.add(key in profile, f"profiledef has {key.rstrip('=')}")
    rep.add("uefi.systemd-boot" in profile and "bios.syslinux" in profile,
            "boots on UEFI and BIOS")


def check_targets(rep: Report) -> None:
    print("\ntarget profiles")
    root = ROOT / "iso/targets"
    confs = sorted(root.glob("*/target.conf")) if root.is_dir() else []
    rep.add(bool(confs), f"{len(confs)} target profile(s) present")

    for conf in confs:
        tdir = conf.parent
        name = tdir.name
        text = conf.read_text("utf-8")
        rep.add(f'BUNNY_TARGET_ID="{name}"' in text,
                f"target {name}: id matches directory")
        for key in ("BUNNY_TARGET_NAME", "BUNNY_ISO_BASENAME",
                    "BUNNY_GAMESCOPE_ARGS", "BUNNY_KERNEL_ARGS"):
            rep.add(f"{key}=" in text, f"target {name}: {key}")

        pkg_file = tdir / "packages.x86_64"
        if pkg_file.is_file():
            packages = [ln.strip() for ln in pkg_file.read_text("utf-8").splitlines()
                        if ln.strip() and not ln.lstrip().startswith("#")]
            bad = [p for p in packages if p in FORBIDDEN_PKGS]
            rep.add(not bad, f"target {name}: no AUR-only packages", ", ".join(bad))
            invalid = [p for p in packages
                       if not re.fullmatch(r"[a-z0-9@._+-]+", p)]
            rep.add(not invalid, f"target {name}: {len(packages)} package names well formed",
                    ", ".join(invalid[:5]))

    deck = ROOT / "iso/targets/deck"
    deck_conf = deck / "target.conf"
    if deck_conf.is_file():
        text = deck_conf.read_text("utf-8")
        rep.add("1280 -H 800" in text, "Steam Deck LCD renders at 1280x800")
        rep.add("amd_pstate=active" in text, "Steam Deck target sets amd_pstate=active")
        deck_pkgs = (deck / "packages.x86_64").read_text("utf-8")
        for pkg in ("fwupd", "alsa-utils", "wireless-regdb", "evtest"):
            rep.add(re.search(rf"(?m)^{pkg}$", deck_pkgs) is not None,
                    f"Steam Deck packages {pkg}")
        rep.add("steamdeck-dkms" not in [ln.strip() for ln in deck_pkgs.splitlines()
                                          if ln.strip() and not ln.lstrip().startswith("#")],
                "no Valve/AUR kernel package in the Deck image")
        rep.add((deck / "airootfs/etc/systemd/zram-generator.conf").is_file(),
                "Steam Deck zram configuration shipped")

    session = (ROOT / "system/bin/bunny-session").read_text("utf-8")
    rep.add("/etc/bunny/target.conf" in session, "session reads per-target config")
    installer = (ROOT / "installer/bunny-install").read_text("utf-8")
    rep.add("BUNNY_KERNEL_ARGS" in installer, "installer carries target kernel args")

    steamdeck = ROOT / "docs/STEAMDECK.md"
    if steamdeck.is_file():
        text = steamdeck.read_text("utf-8").lower()
        rep.add("lcd" in text and "oled" in text, "Deck doc scopes LCD vs OLED")
        rep.add("recovery" in text, "Deck doc covers SteamOS recovery")
        rep.add("bunnyos-deck-installer.iso" in text, "Deck doc names the artefact")
        rep.add("dual" in text, "Deck doc states the dual-boot position")


def check_ai_safety(rep: Report) -> None:
    print("\nBun Bun safety invariants")
    policy = (ROOT / "bunbun/bunbun/mam/policy.py").read_text("utf-8")
    for needle, label in (
        ("anticheat", "anti-cheat titles denied"),
        ("competitive", "competitive modes denied"),
        ("coop_opt_in", "multiplayer requires opt-in"),
        ("input-token", "input requires the root token"),
        ("kid-safe-chat", "kid-safe persona blocks stranger chat"),
    ):
        rep.add(needle in policy, label)

    agent = (ROOT / "bunbun/bunbun/action/coop.py").read_text("utf-8")
    rep.add("player_confirmed" in agent, "co-op join requires player confirmation")
    rep.add("joinlobby" in agent, "Steam lobby deep link implemented")

    service = (ROOT / "bunbun/bunbun/service.py").read_text("utf-8")
    rep.add("127.0.0.1" in service, "agent binds loopback only")
    rep.add("local_only" in service, "agent advertises local-only mode")


def check_ui(rep: Report) -> None:
    print("\ncontrol panel")
    html = (ROOT / "control-panel/ui/index.html").read_text("utf-8")
    for needle, label in (
        ('id="app"', "app mount point"),
        ("js/app.js", "app module loaded"),
        ("data-focusable", "controller focus markers"),
        ("Bun Bun", "Bun Bun panel entry"),
    ):
        rep.add(needle in html, label)

    app_js = (ROOT / "control-panel/ui/js/app.js").read_text("utf-8")
    rep.add("gamepad" in app_js.lower(), "gamepad navigation wired")
    rep.add("fallback" in app_js.lower() or "mock" in app_js.lower(),
            "offline/mock fallback for the UI")

    tauri = json.loads((ROOT / "control-panel/src-tauri/tauri.conf.json").read_text("utf-8"))
    rep.add(bool(tauri.get("app") or tauri.get("tauri")), "Tauri config parsed")
    rep.add(bool(tauri.get("app", {}).get("withGlobalTauri")), "Tauri global API enabled")
    api_js = (ROOT / "control-panel/ui/js/api.js").read_text("utf-8")
    rep.add("_invoke('bunny_call'" not in api_js, "native calls not double-wrapped")
    cargo = (ROOT / "control-panel/src-tauri/Cargo.toml").read_text("utf-8")
    rep.add("tauri" in cargo, "Tauri dependency declared")

    sessiond = (ROOT / "system/lib/bunny_sessiond.py").read_text("utf-8")
    rep.add("refresh_sddm" in sessiond and "[Autologin]" in sessiond,
            "autologin drop-in is daemon-owned")


def check_build(rep: Report) -> None:
    print("\nbuild pipeline")
    script = (ROOT / "build_bunny_os_iso.sh").read_text("utf-8")
    for needle, label in (
        ("BunnyOS-installer.iso", "final artefact name"),
        ("mkarchiso", "mkarchiso invoked"),
        ("validate-profile.sh", "validation stage wired"),
        ("stage-profile.sh", "staging stage wired"),
        ("build-manifest.json", "build manifest emitted"),
        ("--dry-run", "dry-run supported"),
        ("--target", "target profiles supported"),
        ("iso/targets", "target directory wired"),
    ):
        rep.add(needle in script, label)

    stage = (ROOT / "scripts/stage-profile.sh").read_text("utf-8")
    for payload in ("system/bin", "system/units", "bunbun", "control-panel/ui"):
        rep.add(payload in stage, f"stages {payload}")
    rep.add("--target" in stage and "packages.x86_64" in stage,
            "staging merges target overlay and packages")
    rep.add('[[ "${AIR}" != "/" ]]' in stage or "safe_rmrf" in stage,
            "staging cannot delete /")

    workflow = (ROOT / ".github/workflows/build-iso.yml").read_text("utf-8")
    rep.add("--target" in workflow, "CI can build a target profile")
    rep.add("inputs.target" in workflow, "CI exposes a target input")

    # Boot entries may only reference files that archiso actually places in the
    # image. When the initramfs already embeds microcode, archiso sets
    # need_external_ucodes=0 and never copies /arch/boot/*-ucode.img, so an entry
    # pointing at one fails at boot with "Error preparing initrd: Not found".
    boot_refs: list[str] = []
    for conf in (
        ROOT / "iso/overrides/efiboot/loader/entries/01-bunny-os.conf",
        ROOT / "iso/targets/deck/overlay/efiboot/loader/entries/01-bunny-os.conf",
        ROOT / "iso/overrides/syslinux/syslinux.cfg",
    ):
        for line in conf.read_text("utf-8").splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0].lower() in ("linux", "initrd"):
                boot_refs.append(parts[1])
    stray = [r for r in boot_refs if not r.startswith("/arch/boot/") or r.endswith("-ucode.img")]
    rep.add(not stray, "boot entries reference only files archiso ships")
    rep.add("Verifying boot entry paths" in script, "build verifies boot entry paths")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    print("\033[1;35mBunny OS repository verification\033[0m")
    print(f"root: {ROOT}")
    rep = Report(strict=args.strict)
    for check in (check_required, check_json, check_units, check_desktop,
                  check_line_endings, check_packages, check_targets,
                  check_ai_safety, check_ui, check_build):
        check(rep)

    print()
    total = len(rep.checks)
    passed = sum(1 for c in rep.checks if c["status"] == "pass")
    print(f"{passed}/{total} checks passed, {len(rep.warnings)} warnings, "
          f"{len(rep.failures)} failures")

    if args.json:
        print(json.dumps({"checks": rep.checks,
                          "failures": len(rep.failures),
                          "warnings": len(rep.warnings)}, indent=2))
    return 1 if rep.failures else 0


if __name__ == "__main__":
    sys.exit(main())
