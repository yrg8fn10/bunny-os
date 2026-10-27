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
    "system/bin/bunny-desktop-greeting",
    "system/bin/bunny-desktop-theme",
    "iso/airootfs/usr/share/backgrounds/bunny-os/bunny-meadow.png",
    "system/bin/bunny-panel",
    "system/bin/bunny-panel-bridge",
    "system/bin/bunnyctl",
    "system/bin/bunny-firstboot",
    "system/bin/bunny-account-setup",
    "system/bin/bunny-setupd",
    "tools/setupd-smoke.py",
    "system/bin/bunny-recovery",
    "system/bin/bunny-update",
    "system/bin/bunny-health",
    "system/lib/bunny_sessiond.py",
    "system/lib/bunny_input_agent.py",
    "system/units/bunny-sessiond.service",
    "system/units/bunny-firstboot.service",
    "system/units/bunny-setup.service",
    "system/units/bunny-setupd.service",
    "system/units/bunny-recovery.service",
    "system/units/bunny-update.service",
    "system/units/bunny-update.timer",
    "system/units/bunny-health.service",
    "system/units/bunny-health.timer",
    "system/units/bunny-input-agent.service",
    "system/user-units/bunny-bunbun.service",
    "system/wayland-sessions/bunny-gaming.desktop",
    "system/wayland-sessions/bunny-desktop.desktop",
    "system/wayland-sessions/bunny-setup.desktop",
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
    "control-panel/ui/css/pastel.css",
    "control-panel/ui/js/companion.js",
    "control-panel/ui/js/quickmenu.js",
    "control-panel/ui/setup/index.html",
    "control-panel/ui/setup/setup.css",
    "control-panel/ui/setup/setup.js",
    "tools/setup-smoke.html",
    "control-panel/ui/assets/bunny.svg",
    "control-panel/src-tauri/Cargo.toml",
    "control-panel/src-tauri/tauri.conf.json",
    "launchers/bin/bunny-launcher",
    "launchers/bin/bunny-platform-scan",
    "installer/bunny-install",
    "iso/targets/deck/target.conf",
    "iso/targets/deck/packages.x86_64",
    "iso/overrides/efiboot/loader/entries/02-bunny-recovery.conf",
    "iso/overrides/efiboot/loader/entries/03-bunny-setup.conf",
    "iso/targets/deck/overlay/efiboot/loader/entries/01-bunny-os.conf",
    "iso/targets/deck/overlay/efiboot/loader/entries/03-bunny-setup.conf",
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
                    "bunny-firstboot", "bunny-account-setup", "bunny-recovery",
                    "bunny-desktop-greeting", "bunny-desktop-theme",
                    "bunny-update", "bunny-health", "bunny-launcher",
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
    setupd_unit = (ROOT / "system/units/bunny-setupd.service").read_text("utf-8")
    rep.add("User=" not in setupd_unit, "bunny-setupd runs as root (no User= drop)")
    rep.add("Before=display-manager.service" in setupd_unit,
            "setup service is listening before the login manager")
    rep.add("ExecCondition=/usr/local/bin/bunny-setupd --check" in setupd_unit,
            "setup service skips a completed system without failing")
    setupd = (ROOT / "system/bin/bunny-setupd").read_text("utf-8")
    rep.add("--host" in setupd and "127.0.0.1" in setupd,
            "setup service refuses a non-loopback bind")
    rep.add("X-Bunny-Setup" in setupd, "setup API requires the per-boot token")
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
        "iso/overrides/efiboot/loader/entries/02-bunny-recovery.conf",
        "iso/overrides/efiboot/loader/entries/03-bunny-setup.conf",
        "iso/overrides/syslinux/syslinux.cfg",
        "iso/targets/deck/overlay/efiboot/loader/entries/01-bunny-os.conf",
        "iso/targets/deck/overlay/efiboot/loader/entries/03-bunny-setup.conf",
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
    rep.add("oobe" in sessiond and "bunny-setup" in sessiond,
            "session daemon pins first boot to the setup session")
    rep.add("build-info.json" in sessiond, "session daemon reads the baked version")

    # --- first-boot wizard ---------------------------------------------------
    wizard = (ROOT / "control-panel/ui/setup/index.html").read_text("utf-8")
    for needle, label in (
        ('data-focusable', "wizard has controller focus markers"),
        ("__BUNNY_SETUP_TOKEN__", "wizard receives the per-boot token"),
        ("setup.js", "wizard module loaded"),
    ):
        rep.add(needle in wizard, label)
    wizard_js = (ROOT / "control-panel/ui/setup/setup.js").read_text("utf-8")
    for needle, label in (
        ("X-Bunny-Setup", "wizard sends the token header"),
        ("startGamepad", "wizard supports the controller"),
        ("openKeyboard", "wizard has an on-screen keyboard"),
        ("/api/finish", "wizard finishes through the setup service"),
    ):
        rep.add(needle in wizard_js, label)
    rep.add("index.html" in (ROOT / "system/bin/bunny-setupd").read_text("utf-8")
            and "Content-Security-Policy" in (ROOT / "system/bin/bunny-setupd").read_text("utf-8"),
            "setup service serves a locked-down UI")
    wizard_css = (ROOT / "control-panel/ui/setup/setup.css").read_text("utf-8")
    rep.add("--focus" in wizard_css and "@media" in wizard_css,
            "wizard styles a visible focus ring and Deck-sized layouts")

    # Controller reach: the primary button lives in the footer, so navigation
    # must scope the whole frame or a gamepad user can never advance. These two
    # regressions were both found by tools/setup-smoke.html.
    rep.add("nav.setScope(frame())" in wizard_js,
            "wizard D-pad scope includes the footer button")
    rep.add("state.account.created) go(" in wizard_js,
            "wizard Continue advances after the account is created")
    rep.add("addEventListener('input'" in wizard_js and "filterZones" in wizard_js,
            "zone search survives step re-renders")
    rep.add("input.hasAttribute('data-keyboard')" in wizard_js
            and "state.keyboard.open" in wizard_js,
            "wizard A/Enter on a text field raises the on-screen keyboard")
    smoke = (ROOT / "tools/setup-smoke.html").read_text("utf-8")
    for needle, label in (
        ("wizard module", "setup smoke boots the real wizard module"),
        ("is-focused", "setup smoke checks controller focus"),
        ("/api/finish", "setup smoke completes the wizard"),
    ):
        rep.add(needle in smoke, label)

    # Version strings have to come from the image, never from a literal that a
    # previous release forgot to bump.
    bridge = (ROOT / "system/bin/bunny-panel-bridge").read_text("utf-8")
    for rel, content in (
        ("control-panel/ui/js/app.js", app_js),
        ("control-panel/ui/js/mock.js",
         (ROOT / "control-panel/ui/js/mock.js").read_text("utf-8")),
        ("control-panel/ui/setup/setup.js", wizard_js),
        ("system/lib/bunny_sessiond.py", sessiond),
        ("system/bin/bunny-panel-bridge", bridge),
    ):
        rep.add("0.1.0" not in content, f"{rel} has no stale 0.1.0 literal")
    rep.add("build-info.json" in bridge and "target_name" in bridge,
            "panel bridge reports the baked version and target")
    settings_js = (ROOT / "control-panel/ui/js/views/settings.js").read_text("utf-8")
    rep.add("target_name" in settings_js and "build_id" in settings_js,
            "About screen shows version, target and build")

    # --- skin, quick access, companion ---------------------------------------
    rep.add("css/pastel.css" in html, "pastel skin stylesheet linked")
    rep.add("quick-menu" in html, "carrot button wired in the shell")
    quick_js = (ROOT / "control-panel/ui/js/quickmenu.js").read_text("utf-8")
    for label in ("Power", "Library", "Quick settings", "Home"):
        rep.add(label in quick_js, f"quick menu offers {label}")
    rep.add("nav.setScope" in quick_js, "quick menu integrates with spatial focus")
    rep.add("op ? 'power' : 'navigate'" in quick_js,
            "quick menu power tiles dispatch the power action")
    rep.add("createQuickMenu" in app_js, "quick menu instantiated by the shell")
    rep.add("'quick-menu'" in app_js, "quick menu reachable from the action map")

    companion_js = (ROOT / "control-panel/ui/js/companion.js").read_text("utf-8")
    rep.add("createCompanion" in app_js, "companion instantiated by the shell")
    rep.add("setScreen" in app_js, "companion receives screen state")
    rep.add("camera" in companion_js.lower() and "no camera" in companion_js.lower()
            or "No webcam" in companion_js,
            "companion documents screen-state (not camera) tracking")
    rep.add("watcher" in app_js, "companion reads the active app from the watcher")
    pastel = (ROOT / "control-panel/ui/css/pastel.css").read_text("utf-8")
    rep.add("--pink" in pastel and "carrot-button" in pastel,
            "pastel palette and carrot button styled")
    rep.add(".companion" in pastel, "companion positioned by the skin")

    gamepad = (ROOT / "control-panel/ui/js/gamepad.js").read_text("utf-8")
    rep.add("quick-menu" in gamepad, "LB+RB opens the quick menu")

    # --- desktop workspace ---------------------------------------------------
    wall = ROOT / "iso/airootfs/usr/share/backgrounds/bunny-os/bunny-meadow.png"
    rep.add(wall.is_file() and wall.stat().st_size > 10_000,
            "pastel desktop wallpaper shipped")
    theme = (ROOT / "system/bin/bunny-desktop-theme").read_text("utf-8")
    rep.add("plasma-apply-wallpaperimage" in theme, "wallpaper applied through Plasma")
    rep.add(wall.name in theme, "theme script points at the shipped wallpaper")
    sess_text = (ROOT / "system/bin/bunny-session").read_text("utf-8")
    rep.add("apply_desktop_theme" in sess_text, "desktop session applies the theme")
    rep.add((ROOT / "tools/make-wallpaper.py").is_file(),
            "wallpaper is reproducible from source")


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
    rep.add("/etc/bunny/version" in stage and "build-info.json" in stage,
            "staging writes the version file the UI and daemons read")
    rep.add('[[ "${AIR}" != "/" ]]' in stage or "safe_rmrf" in stage,
            "staging cannot delete /")

    # render_tokens only rewrites the file types in its find expression. The
    # BIOS menu is syslinux.cfg, so omitting *.cfg shipped a literal @VERSION@.
    common = (ROOT / "scripts/lib/common.sh").read_text("utf-8")
    rep.add("-name '*.conf'" in common and "-name '*.cfg'" in common,
            "staging renders *.cfg boot menus (syslinux.cfg)")
    rep.add("-name 'os-release'" in common and "-name 'motd'" in common,
            "staging renders /etc/os-release and the motd")

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
        ROOT / "iso/overrides/efiboot/loader/entries/02-bunny-recovery.conf",
        ROOT / "iso/overrides/efiboot/loader/entries/03-bunny-setup.conf",
        ROOT / "iso/targets/deck/overlay/efiboot/loader/entries/01-bunny-os.conf",
        ROOT / "iso/targets/deck/overlay/efiboot/loader/entries/03-bunny-setup.conf",
        ROOT / "iso/overrides/syslinux/syslinux.cfg",
    ):
        for line in conf.read_text("utf-8").splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0].lower() in ("linux", "initrd"):
                boot_refs.append(parts[1])
    stray = [r for r in boot_refs if not r.startswith("/arch/boot/") or r.endswith("-ucode.img")]
    rep.add(not stray, "boot entries reference only files archiso ships")
    rep.add("Verifying boot entry paths" in script, "build verifies boot entry paths")

    # The live image boots straight to Gaming Mode, so the wizard needs an
    # explicit preview path: bunny.oobe=1 makes bunny-setupd ignore the live
    # .oobe-done marker. It must stay a separate entry, never the default.
    preview = (ROOT / "iso/overrides/efiboot/loader/entries/03-bunny-setup.conf").read_text("utf-8")
    rep.add("bunny.oobe=1" in preview, "setup preview boot entry passes bunny.oobe=1")
    deck_preview = (ROOT / "iso/targets/deck/overlay/efiboot/loader/entries/"
                    "03-bunny-setup.conf").read_text("utf-8")
    rep.add("bunny.oobe=1" in deck_preview and "amd_pstate=active" in deck_preview,
            "Deck setup preview keeps the target kernel arguments")
    rep.add("bunny-setup" in (ROOT / "iso/overrides/syslinux/syslinux.cfg").read_text("utf-8"),
            "BIOS menu has a setup preview entry")

    # With no root= on the command line, systemd enables gpt-auto discovery and
    # creates a unit for /dev/gpt-auto-root. The archiso hook has already
    # mounted the live root by label, so that unit can never succeed; on a Steam
    # Deck, whose internal disk carries SteamOS root partitions, it times out
    # and the live system drops into emergency mode. Every entry has to opt out.
    cmdlines: list[str] = []
    for conf in (
        ROOT / "iso/overrides/efiboot/loader/entries/01-bunny-os.conf",
        ROOT / "iso/overrides/efiboot/loader/entries/02-bunny-recovery.conf",
        ROOT / "iso/overrides/efiboot/loader/entries/03-bunny-setup.conf",
        ROOT / "iso/targets/deck/overlay/efiboot/loader/entries/01-bunny-os.conf",
        ROOT / "iso/targets/deck/overlay/efiboot/loader/entries/03-bunny-setup.conf",
        ROOT / "iso/overrides/syslinux/syslinux.cfg",
    ):
        for line in conf.read_text("utf-8").splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0].lower() in ("options", "append"):
                cmdlines.append(line)
    no_optout = [l for l in cmdlines if "systemd.gpt_auto=0" not in l]
    rep.add(bool(cmdlines) and not no_optout,
            "boot entries disable gpt-auto root discovery",
            f"{len(no_optout)} entry(ies) missing systemd.gpt_auto=0")
    with_root = [l for l in cmdlines if any(t.startswith("root=") for t in l.split())]
    rep.add(not with_root,
            "boot entries leave root= to the archiso hook",
            "root= makes systemd target the FAT32 volume instead of the squashfs")

    # archiso mounts the live root from its own initramfs hook. That hook only
    # ends up in the image when mkinitcpio-archiso is installed and its drop-in
    # is present; otherwise mkinitcpio writes a stock Arch initramfs that cannot
    # find airootfs.sfs at all.
    pkgs = (ROOT / "iso/packages.x86_64").read_text("utf-8").splitlines()
    pkgs = [l.strip() for l in pkgs if l.strip() and not l.strip().startswith("#")]
    rep.add("mkinitcpio-archiso" in pkgs, "packages.x86_64 lists mkinitcpio-archiso")
    dropin = ROOT / "iso/airootfs/etc/mkinitcpio.conf.d/archiso.conf"
    rep.add(dropin.is_file(), "profile ships the archiso mkinitcpio drop-in")
    hooks_line = ""
    if dropin.is_file():
        for line in dropin.read_text("utf-8").splitlines():
            if line.strip().startswith("HOOKS="):
                hooks_line = line
    for hook in ("udev", "memdisk", "archiso"):
        rep.add(f" {hook} " in f" {hooks_line} " or f" {hook})" in hooks_line,
                f"archiso HOOKS includes {hook}")
    rep.add("initramfs can mount the live root" in script,
            "build verifies the initramfs carries the archiso hook")


def check_recovery(rep: Report) -> None:
    print("\naccount, recovery and offline boot")
    text = lambda rel: (ROOT / rel).read_text("utf-8")

    # --- account provisioner -------------------------------------------------
    acct = text("system/bin/bunny-account-setup")
    rep.add("useradd" in acct and "chpasswd" in acct,
            "account setup creates a user with a password")
    rep.add('[[ ! -t 0 ]]' in acct,
            "account setup exits cleanly without a terminal")
    rep.add("/etc/sddm.conf.d/20-bunny-session.conf" in acct,
            "account setup repoints SDDM at the new account")
    rep.add(".oobe-done" in acct,
            "account fallback also settles the wizard marker")
    rep.add("setup|bunny-setup" in acct,
            "account fallback never mistakes the kiosk account for a user")
    setup = text("system/units/bunny-setup.service")
    rep.add("Before=display-manager.service" in setup,
            "account setup runs before the login manager")
    rep.add("ConditionPathExists=!/var/lib/bunny/.account-ready" in setup,
            "account setup is skipped once an account exists")
    # The text unit still exists as a manual fallback, but the image must not
    # enable it: the graphical wizard owns first boot now.
    boot = text("iso/airootfs/root/customize_airootfs.sh")
    rep.add("systemctl enable bunny-setupd.service" in boot,
            "live image enables the graphical setup service")
    rep.add("systemctl disable bunny-setup.service" in boot,
            "live image leaves the text account prompt disabled")
    rep.add("useradd -m -c \"Bunny OS Setup\"" in boot and "passwd -l setup" in boot,
            "live image creates a locked kiosk account")
    rep.add(".oobe-done" in boot,
            "live image boots to Gaming Mode, not the wizard")

    # --- recovery menu -------------------------------------------------------
    rec = text("system/bin/bunny-recovery")
    rec_code = "\n".join(l for l in rec.splitlines()
                         if not l.lstrip().startswith("#"))
    rep.add("--disk" in rec_code, "recovery menu offers a clean install")
    rep.add("--keep-home-from" in rec_code, "recovery menu offers a home-preserving migration")
    rep.add("mkinitcpio -P" in rec_code and "bootctl" in rec_code,
            "recovery menu can rebuild initramfs and bootloader")
    rep.add("fsck.vfat" in rec_code and "loader/entries" in rec_code,
            "recovery menu checks filesystems and boot entries")
    recunit = text("system/units/bunny-recovery.service")
    rep.add("ConditionKernelCommandLine=bunny.recovery=1" in recunit,
            "recovery menu only starts from its boot entry")
    rep.add("TTYPath=/dev/tty1" in recunit, "recovery menu owns its own console")

    # The menu used to call `disk="$(pick_disk)"`, which captured the numbered
    # disk list along with the device name. The confirmation could then never
    # match, so every action cancelled itself silently and the menu redrew -
    # the "replace Bunny OS does nothing" loop. The picker must communicate
    # through a global and must never print to stdout.
    rep.add('"$(pick_disk)"' not in rec_code,
            "recovery picker does not capture its own menu output")
    rep.add("PICKED_DISK=" in rec_code, "recovery picker reports the disk through a global")
    rep.add('PICKED_DISK="${disks[' in rec_code,
            "recovery picker stores only the device name")

    # A menu that exits drops tty1 to a locked root getty, so failures must be
    # survivable: logged with a line number, action kept in a subshell, and a
    # closed stdin redraws instead of ending the loop.
    rep.add("trap 'on_error" in rec_code and "${LINENO}" in rec_code,
            "recovery failures report the failing line")
    rep.add('LOG_FILE="${LOG_DIR}/recovery.log"' in rec_code,
            "recovery menu logs to /run/bunny/recovery.log")
    rep.add("run_action()" in rec_code, "recovery actions run in a subshell")
    rep.add("return 3" in rec_code and "no input (Ctrl-D)" in rec_code,
            "recovery menu survives a closed stdin")
    rep.add(not any(l.strip().startswith("exec /usr/local/bin/bunny-install")
                    for l in rec_code.splitlines()),
            "recovery menu never execs the installer")
    rep.add("run_installer" in rec_code and "tee -a" in rec_code,
            "installer output is mirrored to the recovery log")
    rep.add("--self-test" in rec_code and "self_test()" in rec_code,
            "recovery menu can self-test the environment")
    rep.add("action_account" in rec_code,
            "recovery menu exposes the account fallback")
    rep.add("bunny-account-setup" in rec_code,
            "recovery account fallback runs the real provisioner")
    # tty1 has no getty behind the menu (the unit conflicts it out), so a "q to
    # quit" branch would leave the console blank with no way to log in.
    rep.add("q|Q)" not in rec_code,
            "recovery menu has no key that strands the console")

    # The unit has to hold the console. `StandardInput=tty` loses the race
    # against a starting getty and the unit fails - which looks exactly like a
    # locked recovery environment, and takes the shell with it.
    rep.add("StandardInput=tty-force" in recunit, "recovery unit forces the console")
    rep.add("Restart=on-failure" in recunit and "StartLimitIntervalSec=0" in recunit,
            "recovery unit restarts instead of leaving a bare console")
    rep.add("Type=simple" in recunit,
            "recovery unit is long-running, not oneshot")
    for var in ("PATH=", "HOME=", "TERM="):
        rep.add(f"Environment={var}" in recunit,
                f"recovery unit pins {var.rstrip('=')} for the menu and its shell")
    rep.add("/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" in rec,
            "recovery menu sets PATH before calling any tool")
    rep.add('HOME="${HOME:-/root}"' in rec, "recovery menu gives root a HOME")
    rep.add("-t 0" in rec and "ensure_tty" in rec,
            "recovery shell checks for an interactive terminal first")

    entry = text("iso/overrides/efiboot/loader/entries/02-bunny-recovery.conf")
    rep.add("bunny.recovery=1" in entry, "recovery boot entry passes bunny.recovery=1")
    rep.add("systemd.unit=multi-user.target" in entry,
            "recovery boot entry skips the graphical target")
    rep.add("bunny-recovery" in text("iso/overrides/syslinux/syslinux.cfg"),
            "BIOS menu has a recovery entry")

    # --- installer -----------------------------------------------------------
    inst = text("installer/bunny-install")
    rep.add("--keep-home-from" in inst and "rsync -aHAX" in inst,
            "installer can migrate an existing /home")
    rep.add("bunny-os-recovery.conf" in inst,
            "installer writes a recovery boot entry")
    rep.add(".account-ready" in inst,
            "installer marks the account as provisioned")
    rep.add(".oobe-done" in inst and "userdel bunny" in inst,
            "installer hands first boot to the wizard and drops the live login")
    rep.add("systemctl enable bunny-setupd.service" in inst
            and "systemctl disable bunny-setup.service" in inst,
            "installer enables the wizard, not the text prompt")
    rep.add("Session=bunny-setup" in inst or "SDDM_SESSION=bunny-setup" in inst,
            "installer seeds SDDM with the setup session")
    rep.add("created by the first-boot wizard" in inst,
            "installer no longer asks for an account by default")
    rep.add("systemctl enable bunny-recovery.service" in inst,
            "installer enables the recovery menu for later boots")
    for tool in ("sgdisk", "genfstab", "arch-chroot", "rsync"):
        rep.add(tool in inst, f"installer checks for {tool}")

    # The live image carries archiso's mkinitcpio drop-in (the hooks that mount
    # the USB medium). Copied into an installed system it builds an initramfs
    # that cannot find its root, so the install succeeds and never boots.
    rep.add("rm -f /etc/mkinitcpio.conf.d/archiso.conf" in inst,
            "installer drops archiso's initramfs hooks before mkinitcpio -P")
    rep.add("getent group" in inst,
            "installer only passes groups that exist on the target")
    rep.add("cat > /etc/hosts <<HOSTS" in inst and "127.0.1.1" in inst,
            "installer writes /etc/hosts with the hostname expanded")

    # A console first-boot prompt would take tty1 before SDDM, ask for a time
    # zone and leave a dead prompt behind when it exits. Both the live image
    # and the installed system must never run it.
    live = text("iso/airootfs/root/customize_airootfs.sh")
    rep.add("systemctl mask systemd-firstboot.service" in live,
            "live image masks the console first-boot prompt")
    rep.add("systemctl mask systemd-firstboot.service" in inst,
            "installed system masks the console first-boot prompt")
    rep.add("/usr/share/zoneinfo/UTC" in live,
            "live image pins a time zone, so nothing has to prompt for one")

    # Every tool the installer and the recovery menu call must be installed in
    # the image, or they die at their own preflight on the Deck.
    pkgs = [l.strip() for l in text("iso/packages.x86_64").splitlines()
            if l.strip() and not l.strip().startswith("#")]
    for pkg, why in (("gptfdisk", "sgdisk"), ("arch-install-scripts", "genfstab/arch-chroot"),
                     ("rsync", "rsync"), ("parted", "partprobe"),
                     ("dosfstools", "mkfs.fat/fsck.vfat"), ("btrfs-progs", "mkfs.btrfs"),
                     ("sudo", "the recovery menu re-execs itself as root"),
                     ("bash", "the recovery shell"), ("nano", "editing files from that shell"),
                     ("htop", "inspecting the live system")):
        rep.add(pkg in pkgs, f"image ships {pkg} ({why})")

    # --- offline-tolerant boot ----------------------------------------------
    fbunit = text("system/units/bunny-firstboot.service")
    fbunit_keys = [l for l in fbunit.splitlines() if l.strip() and not l.lstrip().startswith(("#", ";"))]
    rep.add(not any("network-online.target" in l for l in fbunit_keys),
            "first boot does not wait for network-online.target")
    rep.add(any("After=network.target" in l for l in fbunit_keys),
            "first boot only orders after network.target")
    rep.add(any("TimeoutStartSec=" in l for l in fbunit_keys), "first boot is time-boxed")
    fb = text("system/bin/bunny-firstboot")
    rep.add("online()" in fb, "first boot probes connectivity itself")
    rep.add("timeout 180 flatpak" in fb, "flatpak installs are time-boxed")
    rep.add("network-online.target" not in fb, "first boot script never blocks on the network")

    for rel in ("iso/airootfs/root/customize_airootfs.sh", "installer/bunny-install"):
        t = text(rel)
        rep.add("wait-online" in t, f"{rel.split('/')[-1]} masks wait-online units")
        rep.add(".account-ready" in t, f"{rel.split('/')[-1]} writes the account marker")

    # --- session handoff -----------------------------------------------------
    # A Wayland session that exits returns the user to the greeter. That is the
    # login loop, so the gaming session must always end up somewhere usable.
    sess = text("system/bin/bunny-session")
    rep.add("exec gamescope" not in sess,
            "gaming session never replaces itself with gamescope")
    rep.add("start_desktop" in sess and "falling back to the desktop" in sess,
            "gaming session falls back to Plasma instead of the greeter")
    rep.add("start_setup" in sess and "--setup" in sess,
            "setup session hosts the wizard in a kiosk compositor")
    rep.add("cage --" in sess, "setup session prefers cage for the kiosk")
    rep.add("gaming-failures" in sess, "gaming session counts consecutive failures")
    rep.add("/dev/uinput" in sess, "gaming session handles a missing uinput device")
    rep.add("gaming_possible" in sess, "gaming session checks DRM/panel before starting")
    rep.add("desktop" in sess and "startplasma-wayland" in sess,
            "desktop session starts Plasma Wayland")

    modal = ROOT / "iso/airootfs/etc/modules-load.d/bunny-gamescope.conf"
    rep.add(modal.is_file() and "uinput" in modal.read_text("utf-8"),
            "image loads uinput at boot for the cursor grab")

    # --- desktop-mode voice greeting ----------------------------------------
    greet = text("system/bin/bunny-desktop-greeting")
    rep.add("espeak-ng" in greet and "piper" in greet,
            "desktop greeting has a local TTS engine")
    rep.add("STAMP" in greet, "desktop greeting is once per boot")
    rep.add("play_greeting" in sess, "session triggers the desktop greeting")
    persona = text("bunbun/bunbun/data/persona.json")
    rep.add("desktop_greeting" in persona,
            "Bun Bun persona carries desktop greeting lines")
    pkgs2 = [l.strip() for l in text("iso/packages.x86_64").splitlines()
             if l.strip() and not l.strip().startswith("#")]
    rep.add("espeak-ng" in pkgs2, "image ships espeak-ng")


def check_release(rep: Report) -> None:
    print("\nrelease pipeline")
    text = lambda rel: (ROOT / rel).read_text("utf-8")

    ship = ROOT / "scripts/ship-release.sh"
    rep.add(ship.is_file(), "scripts/ship-release.sh exists")
    smoke = ROOT / "tools/recovery-smoke.sh"
    rep.add(smoke.is_file(), "tools/recovery-smoke.sh exists")
    rep.add(smoke.is_file() and "pick_disk" in smoke.read_text("utf-8"),
            "recovery smoke test drives the real disk picker")
    inst_smoke = ROOT / "tools/installer-smoke.sh"
    rep.add(inst_smoke.is_file(), "tools/installer-smoke.sh exists")
    rep.add(inst_smoke.is_file() and "mkinitcpio.conf.d/archiso.conf"
            in inst_smoke.read_text("utf-8"),
            "installer smoke test checks the generated initramfs cleanup")
    ship_text = text("scripts/ship-release.sh") if ship.is_file() else ""
    rep.add("git status --porcelain" in ship_text,
            "ship-release refuses a dirty tree")
    rep.add("tools/verify.py --strict" in ship_text,
            "ship-release runs the same verification as CI")
    rep.add("git tag -a" in ship_text and "git push --quiet origin" in ship_text,
            "ship-release tags and pushes")
    rep.add("build-iso.yml" in ship_text and "gh run watch" in ship_text,
            "ship-release waits for the build workflow")
    rep.add("--dry-run" in ship_text, "ship-release has a dry run")
    rep.add('PYTHON="${PYTHON:-}"' in ship_text,
            "ship-release can be pointed at a specific python")
    # The order matters: a tag pointing at an unverified tree is a published
    # broken image, so verification has to happen before the push.
    if "tools/verify.py --strict" in ship_text and "git tag -a" in ship_text:
        rep.add(ship_text.index("tools/verify.py --strict")
                < ship_text.index("git tag -a"),
                "ship-release verifies before it tags")

    workflow = text(".github/workflows/build-iso.yml")
    rep.add("tools/recovery-smoke.sh" in workflow,
            "CI runs the recovery picker smoke test")
    rep.add("tools/installer-smoke.sh" in workflow,
            "CI parses the installer's generated post-install script")
    rep.add("tools/setupd-smoke.py" in workflow,
            "CI exercises the first-boot setup service")
    rep.add("tools/setupd-smoke.py" in (ROOT / "scripts/ship-release.sh").read_text("utf-8"),
            "release script runs the setup service smoke test")
    rep.add("if: startsWith(github.ref, 'refs/tags/v')" in workflow,
            "release job runs only for version tags")
    rep.add("contents: write" in workflow, "release job may write releases")
    rep.add("GH_REPO:" in workflow,
            "release job sets GH_REPO for gh without a checkout")
    rep.add("--prerelease" in workflow, "dash tags publish as pre-releases")
    rep.add("split -b" in workflow,
            "release job splits an ISO above the 2 GiB asset limit")
    rep.add("READ-ME-FIRST.txt" in workflow, "release job ships join instructions")
    rep.add("'deck'" in workflow,
            "a tagged build defaults to the Deck profile")

    build_doc = text("docs/BUILD.md")
    rep.add("ship-release.sh" in build_doc, "BUILD.md documents the release script")
    rep.add("READ-ME-FIRST" in build_doc or ".part" in build_doc,
            "BUILD.md documents the split release assets")


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
                  check_ai_safety, check_ui, check_recovery, check_build,
                  check_release):
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
