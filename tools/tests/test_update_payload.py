#!/usr/bin/env python3
"""Tests for the Bun Bun payload self-updater (bunny-update-payload).

Run directly:  python3 tools/tests/test_update_payload.py
Covers the version comparator, manifest validation, and a full sandbox
update: fake payload -> manifest -> install into a throwaway root.
"""
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
UPDATER = os.path.join(HERE, "..", "..", "system", "bin", "bunny-update-payload")

from importlib.machinery import SourceFileLoader
_loader = SourceFileLoader("bunny_update_payload", UPDATER)
_spec = importlib.util.spec_from_loader("bunny_update_payload", _loader)
mod = importlib.util.module_from_spec(_spec)
_loader.exec_module(mod)


class VersionTests(unittest.TestCase):
    def test_release_beats_prerelease(self):
        self.assertEqual(mod.version_cmp("0.2.0-beta9", "0.2.0-beta9-pre7"), 1)

    def test_higher_prerelease_number(self):
        self.assertEqual(mod.version_cmp("0.2.0-beta9-pre8", "0.2.0-beta9-pre7"), 1)

    def test_higher_beta_beats_lower_beta_prerelease(self):
        self.assertEqual(mod.version_cmp("0.2.0-beta10-pre1", "0.2.0-beta9-pre7"), 1)

    def test_core_version_wins(self):
        self.assertEqual(mod.version_cmp("0.3.0", "0.2.0-beta9"), 1)

    def test_equal_case_insensitive(self):
        self.assertEqual(mod.version_cmp("0.2.0-BETA9-PRE7", "0.2.0-beta9-pre7"), 0)

    def test_rc_and_stable(self):
        self.assertEqual(mod.version_cmp("0.2.0", "0.2.0-rc1"), 1)
        self.assertEqual(mod.version_cmp("0.2.0-rc2", "0.2.0-rc1"), 1)


def make_payload(root, version, marker):
    """Build a tiny fake payload tarball + manifest in root."""
    stage = os.path.join(root, "stage-%s" % version)
    top = os.path.join(stage, "bunny-os-portable-%s" % version)
    os.makedirs(os.path.join(top, "agent", "bunbun"))
    os.makedirs(os.path.join(top, "agent", "bin"))
    os.makedirs(os.path.join(top, "bunhud", "assets"))
    with open(os.path.join(top, "VERSION"), "w") as f:
        f.write(version + "\n")
    with open(os.path.join(top, "build-manifest.json"), "w") as f:
        json.dump({"build_id": "20261109"}, f)
    with open(os.path.join(top, "agent", "bunbun", "service.py"), "w") as f:
        f.write("MARKER = %r\n" % marker)
    cli = os.path.join(top, "agent", "bin", "bunbun-cli")
    with open(cli, "w") as f:
        f.write("#!/bin/sh\necho bun\n")
    os.chmod(cli, 0o755)
    with open(os.path.join(top, "bunhud", "bunhud.py"), "w") as f:
        f.write("# bunhud %s\n" % marker)
    archive = os.path.join(root, "bunny-os-portable-%s.tar.gz" % version)
    with tarfile.open(archive, "w:gz") as t:
        t.add(top, arcname=os.path.basename(top))
    h = hashlib.sha256()
    with open(archive, "rb") as f:
        h.update(f.read())
    manifest = {
        "manifest_version": 1,
        "version": version,
        "sequence": 20261109,
        "payload": {"name": os.path.basename(archive),
                    "size": os.path.getsize(archive), "sha256": h.hexdigest()},
    }
    with open(os.path.join(root, "MANIFEST.json"), "w") as f:
        json.dump(manifest, f)
    return manifest


class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="bunupd-test-")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.opt = os.path.join(self.root, "opt", "bunbun")
        self.etc = os.path.join(self.root, "etc", "bunny")
        self.state = os.path.join(self.root, "var", "lib", "bunny", "updates")
        self.bin = os.path.join(self.root, "usr", "local", "bin")

    def run_updater(self, extra=()):
        return subprocess.run(
            [sys.executable, UPDATER, "--url", "file://" + os.path.join(self.root, "MANIFEST.json"),
             "--opt-dir", self.opt, "--etc-dir", self.etc, "--state-dir", self.state,
             "--bin-dir", self.bin, "--no-restart", "--no-pylibs", "--no-probe"] + list(extra),
            capture_output=True, text=True)

    def test_full_update_then_noop_then_newer(self):
        make_payload(self.root, "0.2.0-beta9-pre7", "v1")
        r = self.run_updater(["--yes"])
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        svc = open(os.path.join(self.opt, "bunbun", "service.py")).read()
        self.assertIn("v1", svc)
        info = json.load(open(os.path.join(self.etc, "build-info.json")))
        self.assertEqual(info["version"], "0.2.0-beta9-pre7")
        self.assertTrue(os.path.islink(os.path.join(self.bin, "bunbun")))

        r = self.run_updater(["--yes"])
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("up to date", r.stdout)

        make_payload(self.root, "0.2.0-beta9", "v2")
        r = self.run_updater(["--yes"])
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        svc = open(os.path.join(self.opt, "bunbun", "service.py")).read()
        self.assertIn("v2", svc)
        info = json.load(open(os.path.join(self.etc, "build-info.json")))
        self.assertEqual(info["version"], "0.2.0-beta9")

    def test_bad_checksum_refuses(self):
        make_payload(self.root, "0.2.0-beta9-pre7", "v1")
        manifest = json.load(open(os.path.join(self.root, "MANIFEST.json")))
        manifest["payload"]["sha256"] = "0" * 64
        json.dump(manifest, open(os.path.join(self.root, "MANIFEST.json"), "w"))
        r = self.run_updater(["--yes"])
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(os.path.isdir(self.opt),
                         "a corrupt payload must not touch the installed tree")

    def test_check_mode_changes_nothing(self):
        make_payload(self.root, "0.2.0-beta9-pre7", "v1")
        r = self.run_updater(["--check"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("update available", r.stdout)
        self.assertFalse(os.path.isdir(self.opt))


if __name__ == "__main__":
    unittest.main(verbosity=2)
