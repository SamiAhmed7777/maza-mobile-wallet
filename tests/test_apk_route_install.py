#!/usr/bin/env python3
"""Fixture-based tests for deploy/apk-route-install.py (M6 r2 polish).

The installer targets root-owned caddy configs on samihost; these tests
exercise its classify/apply/restore logic against tmp-dir fixtures by
monkeypatching the module's FILES list and its run() subprocess shim. No
caddy, systemd, or network is touched: the fake run() returns configured
results, so validate/reload failure paths and the restore-everything rollback
are deterministic. Run: python3 tests/test_apk_route_install.py
"""
import contextlib
import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = importlib.util.spec_from_file_location(
    "apk_route_install", os.path.join(REPO, "deploy", "apk-route-install.py"))
inst = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inst)

INDEXER_ANCHOR = inst.ANCHOR


def write_configs(tmpdir, body):
    paths = []
    for i in range(3):
        p = os.path.join(tmpdir, f"cfg{i}")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(body)
        paths.append(p)
    return paths


PLAIN_VHOST = (
    "# mazatest vhost fixture\n"
    "mazatest.sami-host.me {\n"
    + INDEXER_ANCHOR
    + "\tlog {\n\t\tformat json\n\t}\n"
    + "\treverse_proxy 100.98.140.83:18701\n"
    "}\n"
)


def installed_body():
    return PLAIN_VHOST.replace(
        INDEXER_ANCHOR, INDEXER_ANCHOR + inst.route_block("$2a$14$OLD"))


class FakeRun:
    """Records commands; configurable result per command substring."""

    def __init__(self, hash_ok=True, validate_rc=0, reload_rc=0):
        self.calls = []
        self.hash_envs = []
        self.hash_ok = hash_ok
        self.validate_rc = validate_rc
        self.reload_rc = reload_rc

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        if "hash-password" in cmd:
            self.hash_envs.append((kw.get("env") or {}).get("PW"))
            if not self.hash_ok:
                return subprocess.CompletedProcess(
                    cmd, 1, stdout="", stderr="boom")
            return subprocess.CompletedProcess(
                cmd, 0, stdout="$2a$14$NEWFACE", stderr="")
        if "caddy validate" in cmd:
            return subprocess.CompletedProcess(
                cmd, self.validate_rc, stdout="Valid configuration\n" if self.validate_rc == 0 else "",
                stderr="" if self.validate_rc == 0 else "syntax error near line 9\n")
        if "systemctl reload" in cmd:
            return subprocess.CompletedProcess(
                cmd, self.reload_rc, stdout="", stderr="reload failed\n")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")


def run_installer(paths, password="pw-line\n", fake=None):
    fake = fake or FakeRun()
    inst.FILES = paths
    inst.run = fake
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = inst.main(io.StringIO(password))
    return rc, fake, buf.getvalue()


class ApkRouteInstallTest(unittest.TestCase):
    def test_uniform_install(self):
        with tempfile.TemporaryDirectory() as td:
            paths = write_configs(td, PLAIN_VHOST)
            rc, fake, out = run_installer(paths)
            self.assertEqual(rc, 0)
            self.assertIn("ROUTE-INSTALL exit=0", out)  # install mode reports correctly (r2 blocker 3)
            body = open(paths[0], encoding="utf-8").read()
            self.assertIn("handle_path /apk/* {", body)
            self.assertIn("maza $2a$14$NEWFACE", body)
            self.assertEqual(body.count("handle_path /apk/* {"), 1)
            self.assertTrue(body.index("/apk/*") > body.index("/indexer/*"))
            for p in paths[1:]:
                self.assertEqual(open(p, encoding="utf-8").read(), body)

    def test_uniform_rotate_replaces_hash_only(self):
        with tempfile.TemporaryDirectory() as td:
            paths = write_configs(td, installed_body())
            before = open(paths[0], encoding="utf-8").read()
            rc, fake, out = run_installer(paths)
            self.assertEqual(rc, 0)
            self.assertIn("ROUTE-ROTATE exit=0", out)
            after = open(paths[0], encoding="utf-8").read()
            self.assertNotIn("$2a$14$OLD", after)
            self.assertIn("maza $2a$14$NEWFACE", after)
            # nothing outside the hash line changed
            self.assertEqual(
                before.replace("$2a$14$OLD", "$2a$14$NEWFACE"), after)
            self.assertEqual(after.count("handle_path /apk/* {"), 1)

    def test_mixed_state_refused_before_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            paths = write_configs(td, PLAIN_VHOST)
            with open(paths[2], "w", encoding="utf-8") as fh:
                fh.write(installed_body())
            rc, fake, out = run_installer(paths)
            self.assertEqual(rc, 3)
            self.assertEqual(open(paths[0], encoding="utf-8").read(), PLAIN_VHOST)

    def test_rotate_with_zero_hash_lines_refused(self):
        with tempfile.TemporaryDirectory() as td:
            broken = installed_body().replace(
                "\t\t\tmaza $2a$14$OLD\n", "")  # hash line edited out
            paths = write_configs(td, broken)
            rc, fake, out = run_installer(paths)
            self.assertEqual(rc, 3)
            self.assertEqual(open(paths[0], encoding="utf-8").read(), broken)

    def test_validate_failure_restores_all(self):
        with tempfile.TemporaryDirectory() as td:
            paths = write_configs(td, PLAIN_VHOST)
            fake = FakeRun(validate_rc=1)
            rc, fake, out = run_installer(paths, fake=fake)
            self.assertEqual(rc, 2)
            for p in paths:
                self.assertEqual(open(p, encoding="utf-8").read(), PLAIN_VHOST)

    def test_reload_failure_restores_all_and_reloads(self):
        with tempfile.TemporaryDirectory() as td:
            paths = write_configs(td, PLAIN_VHOST)
            fake = FakeRun(reload_rc=1)
            rc, fake, out = run_installer(paths, fake=fake)
            self.assertEqual(rc, 2)
            for p in paths:
                self.assertEqual(open(p, encoding="utf-8").read(), PLAIN_VHOST)
            reloads = [c for c in fake.calls if "systemctl reload" in c]
            self.assertEqual(len(reloads), 2)  # failed attempt + rollback reload

    def test_stdin_hash_failure_aborts_without_argv(self):
        with tempfile.TemporaryDirectory() as td:
            paths = write_configs(td, PLAIN_VHOST)
            fake = FakeRun(hash_ok=False)
            rc, fake2, out = run_installer(paths, fake=fake)
            self.assertEqual(rc, 3)
            for p in paths:
                self.assertEqual(open(p, encoding="utf-8").read(), PLAIN_VHOST)
            self.assertFalse(any("--plaintext" in c for c in fake2.calls),
                             "password must never ride argv")

    def test_password_whitespace_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            paths = write_configs(td, installed_body())
            fake = FakeRun()
            rc, fake, out = run_installer(paths, password="  spaced pw  \n")
            self.assertEqual(rc, 0)
            self.assertEqual(fake.hash_envs, ["  spaced pw  "])

    def test_empty_password_aborts(self):
        with tempfile.TemporaryDirectory() as td:
            paths = write_configs(td, PLAIN_VHOST)
            rc, fake, out = run_installer(paths, password="\n")
            self.assertEqual(rc, 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
