"""M25: app console logging wiring - source-level regression asserts.

The console (AppLog + crypto.LogRing + DiagnosticsActivity) must stay
status-only: no call site may compose a secret value into a log line, the
single HTTP choke point logs route-identity only (never headers/bodies),
AppLog is the ONLY android.util.Log sink in the app, and the status echoes
the simplify pass removed stay removed.
"""
import glob
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "android", "src", "com", "mazawallet")

# Secret-shaped fragments that must never appear inside an AppLog.<level>(...)
# statement. Statement-level (not line-level): multi-line calls are covered.
FORBIDDEN_IN_LOG = ("Authorization", "Bearer", "tokenEt", "mnemonic",
                    "pinEt", "getBytes", "e.getMessage()")

LOG_CALL_RE = re.compile(r"AppLog\.[iwd]\([^;]*?\);", re.DOTALL)
DIRECT_LOG_RE = re.compile(r"(?<![\w.])Log\.(?:w|i|d|e|v)\(")


def read(rel):
    with open(os.path.join(ROOT, rel), "r", encoding="utf-8") as f:
        return f.read()


def all_java_sources():
    return sorted(glob.glob(os.path.join(SRC, "**", "*.java"), recursive=True))


class AppLogWiringTest(unittest.TestCase):

    def test_logring_is_pure_java(self):
        src = read("android/src/com/mazawallet/crypto/LogRing.java")
        imports = [ln.strip() for ln in src.splitlines()
                   if ln.strip().startswith("import ")]
        self.assertTrue(imports, "sanity: LogRing has imports")
        for ln in imports:
            self.assertFalse(ln.startswith("import android."),
                             "LogRing must not import android.*: %s" % ln)
        # Behaviour itself is pinned by the desktop SelfTest (10+ logring
        # checks); these source asserts only guard the purity contract.

    def test_applog_facade_shape(self):
        src = read("android/src/com/mazawallet/AppLog.java")
        self.assertIn("import android.util.Log;", src)
        self.assertIn("LogRing", src)
        self.assertIn('TAG = "MAZA"', src)
        self.assertIn("public static List<String> snapshot()", src)
        self.assertIn("public static int capacity()", src)

    def test_applog_is_the_only_log_sink(self):
        violators = []
        for path in all_java_sources():
            if path.endswith("AppLog.java"):
                continue
            with open(path, encoding="utf-8") as f:
                for i, line in enumerate(f, 1):
                    if DIRECT_LOG_RE.search(line):
                        violators.append("%s:%d: %s"
                                         % (os.path.relpath(path, ROOT), i,
                                            line.strip()))
        self.assertEqual(violators, [],
                         "android.util.Log used outside AppLog.java: %s"
                         % violators)

    def test_no_call_site_logs_secret_values(self):
        # Statement-level scan (M25: multi-line AppLog calls were previously
        # invisible to a line-based scan). Known limitation, acknowledged:
        # string building across statements is not caught - the primary
        # control is the status-only contract + LogRing.scrub, and the
        # desktop SelfTest pins the scrub behaviour itself.
        offenders = []
        for path in all_java_sources():
            with open(path, encoding="utf-8") as f:
                src = f.read()
            for m in LOG_CALL_RE.finditer(src):
                stmt = m.group(0)
                for word in FORBIDDEN_IN_LOG:
                    if word in stmt:
                        line_no = src[:m.start()].count("\n") + 1
                        offenders.append("%s:%d contains %r"
                                         % (os.path.relpath(path, ROOT),
                                            line_no, word))
        self.assertEqual(offenders, [], "secret-shaped log lines: %s"
                         % offenders)

    def test_choke_point_logs_success_and_failure(self):
        src = read("android/src/com/mazawallet/Api.java")
        self.assertIn("Net.normalizePath(path)", src)
        self.assertNotIn("pathOnly", src,
                         "pathOnly was deduplicated into Net.normalizePath")
        self.assertIn("System.nanoTime()", src)
        self.assertIn('AppLog.w(method + " " + Net.normalizePath(path) '
                      '+ " -> FAIL "', src)

    def test_status_echoes_stay_removed(self):
        main = read("android/src/com/mazawallet/MainActivity.java")
        self.assertNotIn("unlock rejected http=", main)
        self.assertNotIn("unlock transport:", main)
        self.assertIn('AppLog.w("unlock bad response")', main)
        sc = read("android/src/com/mazawallet/SelfCustody.java")
        self.assertNotIn("broadcast rejected http=", sc)
        self.assertNotIn("watch import transport error", sc)
        self.assertIn('AppLog.i("watch import count="', sc)
        self.assertIn('AppLog.i("broadcast ok txid=', sc)
        self.assertIn('AppLog.d("send fee stabilized after "', sc)

    def test_seedvault_single_sink(self):
        sv = read("android/src/com/mazawallet/SeedVault.java")
        self.assertNotIn("import android.util.Log;", sv)
        self.assertIsNone(DIRECT_LOG_RE.search(sv),
                          "direct android.util.Log call in SeedVault")
        self.assertIn('AppLog.w("seed migration deferred', sv)

    def test_diagnostics_uses_facade_only(self):
        diag = read("android/src/com/mazawallet/DiagnosticsActivity.java")
        self.assertNotIn("com.mazawallet.crypto.LogRing", diag)
        self.assertIn("AppLog.snapshot()", diag)
        self.assertIn("AppLog.capacity()", diag)
        self.assertIn("protected void onResume()", diag)

    def test_manifest_gating(self):
        mf = read("android/AndroidManifest.xml")
        self.assertIn(".DiagnosticsActivity", mf)
        block = mf[mf.find('android:name=".DiagnosticsActivity"'):]
        self.assertIn('android:exported="false"', block[:200])
        settings = read("android/src/com/mazawallet/SettingsActivity.java")
        self.assertIn("DiagnosticsActivity.class", settings)

    def test_strings_ascii_and_present(self):
        src = read("android/res/values/strings.xml")
        for key in ("settings_diagnostics", "settings_diagnostics_note",
                    "diag_open", "diag_title", "diag_note", "diag_empty",
                    "diag_count", "diag_copy", "diag_copied"):
            self.assertIn('name="%s"' % key, src)
        src.encode("ascii")  # pure ASCII (raises on anything else)

    def test_selftest_covers_logring(self):
        st = read("android/src/com/mazawallet/crypto/SelfTest.java")
        self.assertGreaterEqual(st.count('check("logring:'), 10)

    def test_console_sources_are_ascii(self):
        # House ASCII rule scoped to the files this changeset owns; older
        # files (PinGuard, SeedVault javadoc) carry em-dashes and are ruled
        # by their own lanes.
        for rel in ("android/src/com/mazawallet/crypto/LogRing.java",
                    "android/src/com/mazawallet/AppLog.java",
                    "android/src/com/mazawallet/DiagnosticsActivity.java",
                    "android/src/com/mazawallet/Api.java"):
            with open(os.path.join(ROOT, rel), "rb") as f:
                self.assertTrue(all(b < 128 for b in f.read()),
                                "non-ASCII in %s" % rel)


if __name__ == "__main__":
    unittest.main()
