#!/usr/bin/env python3
"""W3-UX gates: S-5 network hardening (retry table + copy) and W3-a live
theme repaint (session-preserving rebuild).

WHAT THIS FILE OWNS
-------------------
1. THE RETRY TABLE (android/src/com/mazawallet/Net.java). The table is data
   and is read back here: every API path the app calls must have a row, every
   read must have retries, and every spend POST must have exactly one attempt
   (a retry could broadcast the same payment twice). The table is also
   EXECUTED: Net has no Android imports, so this file compiles it with plain
   javac for the desktop JVM and drives the real retry loop (attempt counts,
   backoff growth, rethrown exception, spend = single attempt).
2. THE REPAINT WIRING (android/src/com/mazawallet/MainActivity.java). A
   source contract: the palette-change detection exists, it is hooked into
   onResume, it rebuilds in place, and the file contains no recreate() /
   finish() at all - the token is memory-only, so an activity restart would
   drop the session. Plus: the repaint restores the snapshot, the tab and the
   lock state instead of blanking them.
3. THE COPY (android/res/values/strings.xml). Every failure the user can hit
   has explicit copy that is actually wired, no path echoes a raw exception
   message, and no string tells the user to restart the app.

Run:  python3 -m unittest discover -s tests -v
"""

import os
import re
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ElementTree

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANDROID = os.path.join(REPO_ROOT, "android")
SRC = os.path.join(ANDROID, "src", "com", "mazawallet")
MAIN_ACTIVITY = os.path.join(SRC, "MainActivity.java")
NET = os.path.join(SRC, "Net.java")
SELF_CUSTODY = os.path.join(SRC, "SelfCustody.java")
STRINGS_XML = os.path.join(ANDROID, "res", "values", "strings.xml")

JAVAC = shutil.which("javac")
JAVA = shutil.which("java")

SPEND_PATHS = ("/api/send", "/api/broadcast")
READ_PATHS = ("/api/state", "/api/qr.png", "/api/watch/utxos", "/api/watch/history",
              "/api/price",
              "/api/v0/address", "/api/v0/tx", "/api/v0/block", "/api/v0/proof")


def read_text(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def strip_comments(java):
    """Drop // and /* */ comments so prose can never satisfy a contract."""
    no_block = re.sub(r"/\*.*?\*/", "", java, flags=re.S)
    return re.sub(r"//[^\n]*", "", no_block)


def method_body(java, signature):
    """Body of a Java method, by its declaration signature text."""
    start = java.find(signature)
    if start < 0:
        return ""
    brace = java.find("{", start)
    if brace < 0:
        return ""
    depth = 0
    for index in range(brace, len(java)):
        char = java[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return java[brace + 1:index]
    return ""


def parse_route_table(net_source):
    """Every `new Route("METHOD", "/path", attempts, spend)` in the table."""
    code = strip_comments(net_source)
    rows = re.findall(
        r'new\s+Route\(\s*"([A-Z]+)"\s*,\s*"([^"]+)"\s*,\s*(\d+)\s*,\s*(true|false)\s*\)',
        code)
    return [{"method": m, "path": p, "attempts": int(a), "spend": s == "true"}
            for m, p, a, s in rows]


def strings_keys():
    root = ElementTree.parse(STRINGS_XML).getroot()
    return {element.get("name"): (element.text or "") for element in root
            if element.tag == "string"}


class RetryTableTest(unittest.TestCase):
    """Net's table must describe the whole API surface, not part of it."""

    def setUp(self):
        self.net = read_text(NET)
        self.rows = parse_route_table(self.net)
        self.main = strip_comments(read_text(MAIN_ACTIVITY))

    def test_table_is_not_empty_and_has_no_duplicates(self):
        self.assertGreaterEqual(len(self.rows), 6,
                                "Net's retry table lost rows")
        keys = [(row["method"], row["path"]) for row in self.rows]
        self.assertEqual(len(keys), len(set(keys)),
                         "duplicate route in Net's table: %s" % keys)

    def test_every_api_path_the_host_calls_has_a_row(self):
        hosts = {}
        for name, path in (("MainActivity.java", MAIN_ACTIVITY),
                           ("SelfCustody.java", SELF_CUSTODY)):
            code = strip_comments(read_text(path))
            hosts[name] = set(re.findall(r'"(/api/[^"?]+)', code))
        registered = {row["path"] for row in self.rows}
        for name, used in hosts.items():
            with self.subTest(source=name):
                missing = sorted(used - registered)
                self.assertEqual(missing, [],
                                 "%s calls paths with no retry policy: %s"
                                 % (name, missing))

    def test_spend_posts_are_never_auto_retried(self):
        for path in SPEND_PATHS:
            with self.subTest(path=path):
                rows = [row for row in self.rows if row["path"] == path]
                self.assertEqual(len(rows), 1, "%s must have exactly one row" % path)
                row = rows[0]
                self.assertTrue(row["spend"],
                                "%s moves funds, so it must be flagged spend" % path)
                self.assertEqual(row["attempts"], 1,
                                 "%s must never be retried (double-send risk)" % path)
                self.assertEqual(row["method"], "POST")

    def test_reads_are_retried_with_backoff(self):
        for path in READ_PATHS:
            with self.subTest(path=path):
                rows = [row for row in self.rows if row["path"] == path]
                self.assertEqual(len(rows), 1, "%s must have exactly one row" % path)
                self.assertEqual(rows[0]["method"], "GET", "%s must be a GET" % path)
                self.assertGreaterEqual(rows[0]["attempts"], 2,
                                        "%s must be retried" % path)
                self.assertFalse(rows[0]["spend"])

    def test_idempotent_post_is_retried_but_not_flagged_as_spend(self):
        rows = [row for row in self.rows if row["path"] == "/api/watch/import"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["method"], "POST")
        self.assertGreaterEqual(rows[0]["attempts"], 2)
        self.assertFalse(rows[0]["spend"], "the import dedupes, it does not spend")

    def test_unknown_paths_fail_safe(self):
        self.assertIn("DEFAULT_ATTEMPTS = 1", self.net,
                      "an unregistered path must get exactly one attempt")
        self.assertIn('return new Route(m, p, DEFAULT_ATTEMPTS, false);', self.net)

    def test_every_transport_call_in_the_host_goes_through_net(self):
        """One wrapper per request: a new direct Api.http() call would bypass
        the policy table silently, so the counts must match exactly."""
        direct = len(re.findall(r"Api\.http\(", self.main))
        wrapped = len(re.findall(r"Net\.withRetry\(", self.main))
        self.assertGreater(direct, 0, "MainActivity should still make requests")
        self.assertEqual(direct, wrapped,
                         "every Api.http() in MainActivity must sit inside a "
                         "Net.withRetry() (%d calls, %d wrappers)"
                         % (direct, wrapped))

    def test_host_does_not_roll_its_own_retry_loop(self):
        self.assertNotIn("Thread.sleep(", self.main,
                         "backoff belongs in Net, not in the activity")
        for path in SPEND_PATHS:
            self.assertNotRegex(self.main, r'while\s*\([^)]*\)\s*\{[^}]*%s'
                                % re.escape(path),
                                "a retry loop around %s is a double-send bug" % path)

    def test_net_is_platform_only(self):
        imports = re.findall(r"^import\s+([\w.]+);", self.net, flags=re.M)
        self.assertTrue(imports)
        offenders = [name for name in imports
                     if not name.startswith("java.")]
        self.assertEqual(offenders, [],
                         "Net must stay Android-free so it is testable on the JVM")


class NetJvmProbeTest(unittest.TestCase):
    """Execute the real retry loop on the desktop JVM."""

    PROBE = r"""
package com.mazawallet;

import java.io.IOException;
import java.net.ConnectException;
import java.net.SocketTimeoutException;
import java.net.UnknownHostException;

/** Drives Net's policy table and retry loop; prints FAIL lines on error. */
public final class NetProbe {

    private static int checks = 0;
    private static int fails = 0;

    private static void check(String what, boolean ok) {
        checks++;
        if (!ok) {
            fails++;
            System.out.println("FAIL " + what);
        }
    }

    public static void main(String[] args) throws Exception {
        // ---- table ----
        Net.Route[] rows = Net.routes();
        check("table has rows", rows.length >= 8);
        check("send is spend", Net.routeFor("POST", "/api/send").spend);
        check("send attempts == 1", Net.routeFor("POST", "/api/send").attempts == 1);
        check("broadcast is spend", Net.routeFor("POST", "/api/broadcast").spend);
        check("broadcast attempts == 1",
                Net.routeFor("POST", "/api/broadcast").attempts == 1);
        check("state retried", Net.routeFor("GET", "/api/state").attempts >= 2);
        check("qr query stripped",
                "/api/qr.png".equals(Net.routeFor("GET", "/api/qr.png?addr=M1").path));
        check("method is case-insensitive",
                Net.routeFor("get", "/api/state").attempts >= 2);
        check("unknown path single attempt",
                Net.routeFor("GET", "/api/nope").attempts == 1);
        check("unknown path is not spend",
                !Net.routeFor("GET", "/api/nope").spend);

        // ---- backoff ----
        check("first backoff == base", Net.backoffMs(1) == Net.BASE_BACKOFF_MS);
        check("backoff doubles", Net.backoffMs(2) == 2 * Net.BASE_BACKOFF_MS);
        check("backoff capped", Net.backoffMs(40) == Net.MAX_BACKOFF_MS);
        check("no backoff before attempt 1", Net.backoffMs(0) == 0L);

        // ---- read: retried, last exception rethrown ----
        final int[] readTries = {0};
        IOException readErr = null;
        try {
            Net.withRetry("GET", "/api/state", () -> {
                readTries[0]++;
                throw new ConnectException("refused");
            }, 1L);
            check("read must throw", false);
        } catch (IOException e) {
            readErr = e;
        }
        check("read attempted 3 times", readTries[0] == 3);
        check("last exception is rethrown", readErr instanceof ConnectException);

        // ---- spend: exactly one attempt ----
        final int[] spendTries = {0};
        try {
            Net.withRetry("POST", "/api/send", () -> {
                spendTries[0]++;
                throw new SocketTimeoutException("no answer");
            }, 1L);
            check("spend must throw", false);
        } catch (IOException expected) {
            // expected
        }
        check("spend attempted exactly once", spendTries[0] == 1);

        // ---- success paths ----
        final int[] okTries = {0};
        String value = Net.withRetry("GET", "/api/state", () -> {
            okTries[0]++;
            return "ok";
        }, 1L);
        check("success returns the value", "ok".equals(value));
        check("success does not retry", okTries[0] == 1);

        final int[] flakyTries = {0};
        String second = Net.withRetry("GET", "/api/state", () -> {
            flakyTries[0]++;
            if (flakyTries[0] < 2) throw new IOException("blip");
            return "second";
        }, 1L);
        check("retry then success", "second".equals(second) && flakyTries[0] == 2);

        // ---- classification drives the copy ----
        check("UnknownHost is offline",
                Net.classify(new UnknownHostException("x")) == Net.FAIL_OFFLINE);
        check("SocketTimeout is timeout",
                Net.classify(new SocketTimeoutException("x")) == Net.FAIL_TIMEOUT);
        check("ConnectException is unreachable",
                Net.classify(new ConnectException("x")) == Net.FAIL_UNREACHABLE);
        check("plain IOException is other",
                Net.classify(new IOException("x")) == Net.FAIL_OTHER);

        if (fails > 0) {
            System.out.println(fails + " of " + checks + " NET PROBE CHECKS FAILED");
            System.exit(1);
        }
        System.out.println("ALL NET PROBES PASSED (" + checks + " checks)");
    }
}
"""

    def test_retry_loop_on_desktop_jvm(self):
        if not JAVAC or not JAVA:
            self.skipTest("javac/java unavailable - JVM probe not run")
        workdir = tempfile.mkdtemp(prefix="maza-net-probe-")
        try:
            classes = os.path.join(workdir, "classes")
            os.makedirs(classes)
            sources = {
                "Net.java": read_text(NET),
                "NetProbe.java": self.PROBE,
            }
            for name, body in sources.items():
                with open(os.path.join(workdir, name), "w", encoding="ascii") as handle:
                    handle.write(body)
            compiled = subprocess.run(
                [JAVAC, "-nowarn", "-d", classes]
                + [os.path.join(workdir, name) for name in sources],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
            self.assertEqual(compiled.returncode, 0,
                             "javac failed:\n%s"
                             % compiled.stdout.decode("utf-8", "replace"))
            run = subprocess.run(
                [JAVA, "-classpath", classes, "com.mazawallet.NetProbe"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
            output = run.stdout.decode("utf-8", "replace")
            self.assertEqual(run.returncode, 0, "Net probe failed:\n%s" % output)
            self.assertIn("ALL NET PROBES PASSED", output)
            self.assertNotIn("FAIL ", output)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)


class RepaintWiringTest(unittest.TestCase):
    """W3-a: the repaint exists, is hooked up, and cannot restart the app."""

    def setUp(self):
        self.source = read_text(MAIN_ACTIVITY)
        self.code = strip_comments(self.source)

    def test_on_resume_detects_the_palette_change_first(self):
        body = method_body(self.code, "protected void onResume()")
        self.assertIn("repaintForThemeChange();", body,
                      "onResume must check the palette")
        self.assertIn("pinGuard.onResumeLocked()", body,
                      "the auto-lock bracket must still run on every resume")
        self.assertLess(body.find("repaintForThemeChange();"),
                        body.find("pinGuard.onResumeLocked()"),
                        "the repaint must run before the lock decisions so the "
                        "rebuilt overlay is the one they act on")

    def test_detection_reapplies_the_saved_mode_and_compares_palettes(self):
        body = method_body(self.code, "private void repaintForThemeChange()")
        self.assertIn("ThemeController.applyTheme(this, SettingsActivity.themeMode(prefs))",
                      body,
                      "the repaint must use the same mode entry point as Settings")
        self.assertIn("UiTheme.Palette next = UiTheme.palette(this);", body)
        self.assertIn("if (samePalette(pal, next)) return;", body,
                      "an unchanged palette must NOT trigger a rebuild")
        self.assertIn("repaintInPlace(next);", body)

    def test_same_palette_compares_every_slot(self):
        body = method_body(self.code, "static boolean samePalette(")
        self.assertTrue(body, "samePalette must exist")
        self.assertIn("a.isLight() == b.isLight()", body)
        self.assertIn("if (a == null || b == null) return a == b;", body)
        for slot in ("background", "surface", "bar", "divider", "textPrimary",
                     "textSecondary", "accent", "danger", "success"):
            with self.subTest(slot=slot):
                self.assertEqual(body.count("a.%s() == b.%s()" % (slot, slot)), 1,
                                 "samePalette must compare %s" % slot)

    def test_the_session_path_never_restarts_the_activity(self):
        # The token is memory-only: recreate()/finish() would bounce the user
        # to the Connect card, which is the bug W3-a fixes.
        self.assertNotIn("recreate()", self.code,
                         "a theme repaint must not recreate the activity")
        self.assertNotIn("finish()", self.code.split("private void repaintInPlace")[0],
                         "no finish() anywhere before the repaint path")
        repaint = method_body(self.code, "private void repaintInPlace(")
        self.assertNotIn("recreate()", repaint)
        self.assertNotIn("finish()", repaint)
        self.assertNotIn("startActivity(", repaint)

    def test_repaint_keeps_the_session_and_restores_the_snapshot(self):
        repaint = method_body(self.code, "private void repaintInPlace(")
        self.assertTrue(repaint, "repaintInPlace must exist")
        self.assertIn("final boolean connected = token != null;", repaint)
        self.assertIsNone(re.search(r"\btoken\s*=[^=]", repaint),
                          "the repaint must never clear or reassign the token")
        self.assertIsNone(re.search(r"\bbaseUrl\s*=[^=]", repaint),
                          "the repaint must not touch the endpoint")
        self.assertIn("if (connected == false)", repaint,
                      "the Connect card is a separate, session-free branch")
        self.assertIn("buildWalletUi();", repaint,
                      "the connected branch must re-run the build path")
        self.assertIn("if (state != null) {", repaint)
        self.assertIn("paintState(state, false);", repaint,
                      "the last snapshot must be repainted, not refetched")
        self.assertIn("if (prevTab != 0) selectTab(prevTab);", repaint,
                      "the selected tab must survive the repaint")
        self.assertIn("if (lockShown) showLock();", repaint,
                      "a visible PIN cover must follow the palette too")
        self.assertIn("pal = next;", repaint,
                      "the repaint must swap the palette the builders read")

    def test_repaint_keeps_the_explicit_failure_state_without_a_snapshot(self):
        """W3-a x S-5: a repaint must not turn a failed history fetch into an
        empty list, and a never-loaded balance must stay explicit."""
        repaint = method_body(self.code, "private void repaintInPlace(")
        self.assertIn("} else if (historyErr) {", repaint,
                      "a repaint with no snapshot must restore the failure line")
        self.assertIn("historyFailed(historyMsg);", repaint)
        failed = method_body(self.code, "private void updateFailed(")
        self.assertIn("getString(R.string.balance_unavailable)", failed,
                      "a never-loaded balance must say so, not sit on '...'")
        self.assertIn("historyFailed(getString(R.string.history_failed, reason));",
                      failed)

    def test_build_path_is_side_effect_free_and_reused(self):
        build = method_body(self.code, "private void buildWalletUi()")
        self.assertTrue(build, "buildWalletUi must exist")
        for banned in ("loadQr();", "schedulePoll();", "onUnlocked();", "refresh();"):
            with self.subTest(call=banned):
                self.assertNotIn(banned, build,
                                 "buildWalletUi must not do session work (%s)" % banned)
        show = method_body(self.code, "private void showWallet()")
        self.assertIn("buildWalletUi();", show)
        self.assertEqual(show.count("selfCustody.onUnlocked();"), 1,
                         "the unlock path must still fire the M21 re-import once")

    def test_palette_provenance_is_unchanged(self):
        self.assertIn("pal = UiTheme.palette(this);", self.code)
        self.assertIn("new SelfCustody(this, this, pal)", self.code)


class NetworkCopyTest(unittest.TestCase):
    """S-5: explicit failure copy, no raw exception text, no silent lists."""

    REQUIRED = {
        "offline": "net_error_offline",
        "timeout": "net_error_timeout",
        "unreachable": "net_error_unreachable",
        "generic": "net_error_generic",
        "http_status": "net_error_server",
        "bad_body": "net_bad_response",
        "expired_session": "net_session_expired",
        "invalid_token": "net_invalid_token",
        "update_failed": "net_update_failed",
        "stale_balance": "balance_stale",
        "no_balance": "balance_unavailable",
        "history_loading": "history_loading",
        "history_empty": "history_empty",
        "history_failed": "history_failed",
        "qr_loading": "qr_loading",
        "qr_failed": "qr_failed",
        "qr_bad_image": "qr_bad_image",
        "send_failed": "send_failed",
        "send_unknown": "send_unknown",
    }

    def setUp(self):
        self.strings = strings_keys()
        self.code = strip_comments(read_text(MAIN_ACTIVITY))

    def test_every_failure_has_copy(self):
        for label, key in self.REQUIRED.items():
            with self.subTest(kind=label):
                self.assertIn(key, self.strings, "%s copy is missing" % label)
                self.assertTrue(self.strings[key].strip(),
                                "%s copy is empty" % label)

    def test_copy_is_wired_not_just_declared(self):
        for label, key in self.REQUIRED.items():
            with self.subTest(kind=label):
                self.assertIn("R.string.%s" % key, self.code,
                              "%s is declared but never shown" % label)

    def test_spend_failure_warns_against_a_blind_retry(self):
        text = self.strings["send_unknown"].lower()
        self.assertIn("not confirmed", text)
        self.assertIn("history", text,
                      "the unknown-outcome copy must point at HISTORY, not "
                      "invite a second send")

    def test_no_raw_exception_text_reaches_the_user(self):
        self.assertNotIn("e.getMessage()", self.code,
                         "exception text must be mapped through Net.classify")
        for stale in ("Cannot reach server: \" + ", "Network error: \" + ",
                      "Bad response: \" + "):
            with self.subTest(stale=stale):
                self.assertNotIn(stale, self.code)

    def test_every_referenced_string_exists(self):
        referenced = set(re.findall(r"R\.string\.([a-zA-Z0-9_]+)", self.code))
        self.assertGreater(len(referenced), 10)
        missing = sorted(referenced - set(self.strings))
        self.assertEqual(missing, [], "MainActivity references undefined strings: %s"
                         % missing)

    def test_no_string_asks_the_user_to_restart(self):
        for key, value in self.strings.items():
            with self.subTest(key=key):
                lowered = value.lower()
                for word in ("restart", "relaunch", "re-open the app",
                             "restart the app"):
                    self.assertNotIn(word, lowered,
                                     "%s still implies a restart is needed" % key)

    def test_history_list_has_an_explicit_state_line(self):
        self.assertIn("private TextView historyStatusTv;", self.code)
        build = method_body(self.code, "private void buildHistoryTab()")
        self.assertIn("historyStatusTv = label(getString(R.string.history_loading)",
                      build,
                      "the HISTORY tab must open on an explicit state, not blank")
        render = method_body(self.code, "private void renderHistory(")
        self.assertIn("historyStatusTv.setText(\"\");", render,
                      "a rendered snapshot clears the status line")
        fail = method_body(self.code, "private void historyFailed(")
        self.assertIn("pal.danger()", fail)
        self.assertIn("historyStatusTv.setText(msg);", fail)

    def test_refresh_reports_every_failure_kind(self):
        body = method_body(self.code, "private void refresh()")
        self.assertEqual(body.count("updateFailed("), 3,
                         "HTTP error, transport error and bad body must each "
                         "surface a message")
        self.assertIn("Net.withRetry(\"GET\", \"/api/state\"", body)

    def test_lane_strings_are_ascii(self):
        raw = read_text(STRINGS_XML).encode("ascii", "strict")
        self.assertGreater(len(raw), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class OsDayNightFoldWiring(unittest.TestCase):
    """W3-a follow-up: an OS day/night flip must NOT recreate the activity
    (that would drop the memory-only token and bounce to Connect); it must
    take the same in-place repaint path as the Settings-driven switch."""

    def test_manifest_handles_uimode_without_recreate(self):
        manifest = read_text(os.path.join(REPO_ROOT, "android", "AndroidManifest.xml"))
        self.assertEqual(manifest.count("android:configChanges="), 3,
                         "the three session-bearing activities (Main, "
                         "Settings, Explorer) declare configChanges; "
                         "Diagnostics is intentionally stateless (recreate "
                         "re-themes for free)")
        self.assertNotIn('keyboardHidden">', manifest,
                         "an activity without uiMode would be recreated on a "
                         "day/night flip and drop the session")
        self.assertEqual(manifest.count("keyboardHidden|uiMode"), 2)

    def test_main_activity_repaints_on_configuration_change(self):
        src = read_text(MAIN_ACTIVITY)
        i = src.find("public void onConfigurationChanged(")
        self.assertTrue(i >= 0, "onConfigurationChanged override must exist")
        end = src.find("\n    }\n", i)
        block = src[i:end if end > i else len(src)]
        self.assertIn("super.onConfigurationChanged(newConfig);", block)
        self.assertIn("repaintForThemeChange();", block)


class SelfCustodyRoutesThroughNet(unittest.TestCase):
    """Wave-3 fold: every SelfCustody call site goes through Net.withRetry so
    the ONE retry table governs the whole wallet (previously SelfCustody made
    raw Api.http calls for five paths and hand-rolled its own import loop)."""

    def test_all_selfcustody_paths_route_through_net(self):
        src = read_text(os.path.join(REPO_ROOT, "android", "src",
                                    "com", "mazawallet", "SelfCustody.java"))
        self.assertGreaterEqual(src.count("Net.withRetry("), 6,
                                "six call sites must be routed through Net")
        for path in ("/api/watch/utxos", "/api/watch/history", "/api/qr.png",
                     "/api/broadcast", "/api/watch/import"):
            self.assertIn('Net.withRetry("GET", "%s' % path if path != "/api/broadcast" and path != "/api/watch/import" else 'Net.withRetry("POST", "%s' % path,
                          src, "path %s must be routed via Net.withRetry" % path)
        # broadcast is a spend: its route must stay pinned at one attempt in Net
        net = read_text(os.path.join(REPO_ROOT, "android", "src", "com",
                                     "mazawallet", "Net.java"))
        self.assertRegex(net, r'new Route\("POST", "/api/broadcast", 1, true\)')


    def test_watch_import_has_one_total_retry_budget(self):
        """The import budget is Net's THREE attempts, TOTAL. The pre-Net
        hand-rolled outer loop in ensureWatchImported would have multiplied
        it to nine requests; this pins the loop's removal."""
        src = read_text(os.path.join(REPO_ROOT, "android", "src",
                                    "com", "mazawallet", "SelfCustody.java"))
        i = src.find("private void ensureWatchImported()")
        end = src.find("\n    }\n", i)
        block = src[i:end if end > i else len(src)]
        self.assertNotIn("for (int attempt", block,
                         "no outer retry loop: Net owns the budget (3 total)")
        self.assertNotIn("Thread.sleep", block,
                         "no manual sleep backoff: Net owns the backoff")
        imp = src.find("private boolean importAddresses(")
        imp_end = src.find("\n    }\n", imp)
        imp_block = src[imp:imp_end if imp_end > imp else len(src)]
        self.assertEqual(imp_block.count("Net.withRetry("), 1,
                         "exactly one withRetry wrapper in importAddresses")
        net = read_text(os.path.join(REPO_ROOT, "android", "src", "com",
                                     "mazawallet", "Net.java"))
        self.assertRegex(net, r'new Route\("POST", "/api/watch/import", 3, false\)')
