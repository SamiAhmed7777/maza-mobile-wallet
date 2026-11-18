#!/usr/bin/env python3
"""Wiring contract for M14-i: local receive notifications.

The BEHAVIOR lives where it is executed:
  - the pure decision table (toSats / shouldFire / runtimeRequestNeeded /
    channelNeeded) is driven on the desktop JVM by crypto/SelfTest.java
    notifyPolicyChecks() (30 static check call sites; 26 execute per run
    since each throw scenario runs exactly one of its pair - runtime total
    276; incl. the NaN and first-sample rules);
  - the on-device receive demonstration is a device-lane item (M14-ii).

This file pins the WIRING the SelfTest cannot see: NotifyPolicy purity,
the ReceiveNotify top-level/no-platform-supertype shape (the d8 rule),
the observe call sites on BOTH balance surfaces (bench paintState + the
self-custody applyRefresh), the per-session continuity resets (unlock
never re-announces an old balance; a fresh/imported seed is a new
continuity), the manifest permission + the exact four-permission set
(the beta battery asserts this set), the strings the notification
renders, and the docs honesty (DECISIONS D16: app-alive only, no push,
lock-screen amount exposure; user-guide sections 4 + 11 carry the
same scope).
"""
import os
import re
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POLICY = os.path.join(REPO, "android", "src", "com", "mazawallet",
                      "crypto", "NotifyPolicy.java")
NOTIFY = os.path.join(REPO, "android", "src", "com", "mazawallet",
                      "ReceiveNotify.java")
MAIN = os.path.join(REPO, "android", "src", "com", "mazawallet",
                    "MainActivity.java")
CUSTODY = os.path.join(REPO, "android", "src", "com", "mazawallet",
                       "SelfCustody.java")
MANIFEST = os.path.join(REPO, "android", "AndroidManifest.xml")
STRINGS = os.path.join(REPO, "android", "res", "values", "strings.xml")
SELFTEST = os.path.join(REPO, "android", "src", "com", "mazawallet",
                        "crypto", "SelfTest.java")
DECISIONS = os.path.join(REPO, "DECISIONS.md")
USER_GUIDE = os.path.join(REPO, "docs", "user-guide.md")


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class NotifyPolicyPurity(unittest.TestCase):
    """NotifyPolicy: pure decision class, no Android imports."""

    def setUp(self):
        self.src = read(POLICY)

    def test_no_android_imports(self):
        self.assertNotIn("import android", self.src)
        for banned in ("java.net", "java.io", "java.nio"):
            self.assertNotIn(f"import {banned}", self.src)

    def test_constants(self):
        self.assertIn("public static final long COIN = 100000000L;", self.src)
        self.assertIn('CHANNEL_ID = "incoming_maza"', self.src)
        self.assertIn("public static final int RUNTIME_PERM_API = 33;", self.src)
        self.assertIn("public static final int CHANNEL_API = 26;", self.src)

    def test_decision_surface(self):
        for sym in ("toSats(", "shouldFire(", "runtimeRequestNeeded(",
                    "channelNeeded("):
            self.assertIn(sym, self.src)

    def test_private_constructor(self):
        # Pure policy: no instances.
        self.assertIn("private NotifyPolicy()", self.src)

    def test_first_sample_rule_is_documented(self):
        # The never-re-announce rule must live IN the policy, not just docs.
        self.assertIn("first sample", self.src)
        self.assertIn("STRICT increase", self.src)


class ReceiveNotifyShape(unittest.TestCase):
    """ReceiveNotify: the thin Android shell, d8-rule-safe."""

    def setUp(self):
        self.src = read(NOTIFY)

    def test_top_level_class_no_platform_supertype(self):
        # The d8 nested-class rule: any nested class whose direct supertype
        # resolves to a platform class NPEs during dexing. ReceiveNotify is
        # a top-level final class with NO extends/implements at all.
        self.assertNotIn("class ReceiveNotify extends", self.src)
        self.assertNotIn("class ReceiveNotify implements", self.src)
        decl = [ln.strip() for ln in self.src.splitlines()
                if ln.startswith("public final class ReceiveNotify")]
        self.assertEqual(len(decl), 1, "one top-level declaration")

    def test_uses_the_policy_not_its_own_math(self):
        self.assertIn("NotifyPolicy.toSats(", self.src)
        self.assertIn("NotifyPolicy.shouldFire(", self.src)
        self.assertIn("NotifyPolicy.channelNeeded(", self.src)
        self.assertIn("NotifyPolicy.runtimeRequestNeeded(", self.src)
        self.assertIn("NotifyPolicy.CHANNEL_ID", self.src)

    def test_both_surfaces_observed(self):
        self.assertIn("observeBench(", self.src)
        self.assertIn("observeWallet(", self.src)

    def test_distinct_notification_ids(self):
        self.assertIn("ID_BENCH = 1", self.src)
        self.assertIn("ID_WALLET = 2", self.src)

    def test_malformed_sample_neither_fires_nor_resets(self):
        # observe returns prev on a bad balance: no fire AND no continuity
        # reset (a 0-return would fire on the next good sample).
        self.assertIn("return prev; // malformed sample: no fire, no continuity reset",
                      self.src)

    def test_permission_asked_once_per_session(self):
        self.assertIn("requestIfNeeded(", self.src)
        self.assertIn("alreadyAsked", self.src)
        self.assertIn("android.Manifest.permission.POST_NOTIFICATIONS", self.src)

    def test_channel_created_idempotently(self):
        self.assertIn("getNotificationChannel(NotifyPolicy.CHANNEL_ID) != null", self.src)
        self.assertIn("createNotificationChannel(ch)", self.src)

    def test_enabled_gate_before_fire(self):
        # areNotificationsEnabled() covers the pre-13 master switch and the
        # 13+ runtime grant in one call.
        self.assertIn("areNotificationsEnabled()", self.src)

    def test_notification_carries_no_address_or_txid(self):
        # The text is amount + source only (D16: no address, no txid, no
        # secret ever rides a notification).
        self.assertNotIn("txid", self.src.lower())
        for banned in ("addrTv", "getAddress()", "ws.address"):
            self.assertNotIn(banned, self.src)


class MainActivityWiring(unittest.TestCase):
    """Bench surface: paintState observes; showWallet resets per session."""

    def setUp(self):
        self.src = read(MAIN)

    def test_last_seen_field_memory_only(self):
        self.assertIn("private Long lastBenchSats;", self.src)
        self.assertIn("memory-only per session", self.src)

    def test_paint_state_observes_bench_balance(self):
        self.assertIn("ReceiveNotify.observeBench(this, lastBenchSats, ws.balance)",
                      self.src)
        self.assertIn("lastBenchSats = ReceiveNotify.observeBench(", self.src)

    def test_show_wallet_resets_continuity(self):
        # showWallet = unlock/reconnect only (buildWalletUi's repaint path
        # must NOT reset - a mid-session theme switch keeps continuity).
        self.assertIn("lastBenchSats = null;", self.src)

    def test_show_wallet_creates_channel_and_asks_permission(self):
        self.assertIn("ReceiveNotify.ensureChannel(this);", self.src)
        self.assertIn("notifPermAsked = ReceiveNotify.requestIfNeeded(this, notifPermAsked);",
                      self.src)
        self.assertIn("private boolean notifPermAsked;", self.src)

    def test_reset_is_in_show_wallet_not_build_wallet_ui(self):
        # The reset must sit inside showWallet's body, before the M21 call.
        show = self.src[self.src.index("private void showWallet()"):
                        self.src.index("private void buildWalletUi()")]
        self.assertIn("lastBenchSats = null;", show)
        self.assertIn("ReceiveNotify.ensureChannel(this);", show)
        # And NOT in buildWalletUi (repaint keeps continuity).
        build = self.src[self.src.index("private void buildWalletUi()"):]
        build_tail = build[:build.index("private void paintState(")]
        self.assertNotIn("lastBenchSats = null;", build_tail)


class SelfCustodyWiring(unittest.TestCase):
    """Seed surface: applyRefresh observes; finishSetup resets continuity."""

    def setUp(self):
        self.src = read(CUSTODY)

    def test_last_seen_field_memory_only(self):
        self.assertIn("private Long lastWatchSats;", self.src)

    def test_apply_refresh_observes_watch_balance(self):
        self.assertIn("ReceiveNotify.observeWallet(act, lastWatchSats, balance)",
                      self.src)
        self.assertIn("lastWatchSats = ReceiveNotify.observeWallet(", self.src)

    def test_finish_setup_resets_continuity(self):
        # A fresh/imported seed is a new continuity (D16).
        fin = self.src[self.src.index("private void finishSetup("):]
        self.assertIn("lastWatchSats = null;", fin)


class ManifestAndStrings(unittest.TestCase):
    """Permission + notification copy."""

    def test_post_notifications_declared(self):
        mf = read(MANIFEST)
        self.assertIn('<uses-permission android:name="android.permission.POST_NOTIFICATIONS" />',
                      mf)

    def test_exactly_four_permissions(self):
        mf = read(MANIFEST)
        perms = sorted(set(re.findall(r"android\.permission\.[A-Z_]+", mf)))
        self.assertEqual(perms, ["android.permission.CAMERA",
                                 "android.permission.INTERNET",
                                 "android.permission.POST_NOTIFICATIONS",
                                 "android.permission.USE_BIOMETRIC"])

    def test_notification_strings_present(self):
        src = read(STRINGS)
        for key in ("notify_channel_name", "notify_channel_desc",
                    "notify_title", "notify_src_bench", "notify_src_wallet"):
            self.assertIn(f'name="{key}"', src)
        # Pure ASCII additions.
        block = src[src.index("notify_channel_name"):]
        block = block[:block.index("</resources>")]
        self.assertTrue(all(ord(c) < 128 for c in block),
                        "notification strings are pure ASCII")


class SelfTestRegistration(unittest.TestCase):
    """The decision table is desktop-driven."""

    def test_notify_policy_checks_registered(self):
        src = read(SELFTEST)
        self.assertIn("notifyPolicyChecks();", src)

    def test_row_count_matches_the_decision_surface(self):
        # Count executable check( call sites inside notifyPolicyChecks -
        # the house rule counts call sites, not textual matches of the
        # word (the registration line and javadoc would inflate it).
        # STATIC count is 30: each of the four throw scenarios carries a
        # check(false) in the try AND a check(true) in the catch, and
        # exactly ONE of the pair executes per run - so the runtime total
        # is 26 rows (250 prior + 26 = 276, measured this change).
        src = read(SELFTEST)
        body = src[src.index("private static void notifyPolicyChecks()"):]
        body = body[:body.index("\n    /** GapPolicy")]
        n = len(re.findall(r"\bcheck\(", body))
        self.assertEqual(n, 30, "30 static notifyPolicy check call sites")


class DocsHonesty(unittest.TestCase):
    """D16 + user guide carry the real scope, no overclaim."""

    def test_decisions_d16_exists_with_no_push_claim(self):
        src = read(DECISIONS)
        self.assertIn("## D16 — Local receive notifications", src)
        self.assertIn("App-alive only, no push", src)
        self.assertIn("There is NO push/FCM path", src)
        self.assertIn("First sample never fires", src)
        self.assertIn("Lock-screen exposure is by design", src)

    def test_user_guide_states_app_alive_scope(self):
        src = read(USER_GUIDE)
        self.assertIn("MAZA received", src)
        self.assertIn("It is NOT push", src)
        self.assertIn("app-alive only, not push", src)
        # The old blanket limitation line is gone.
        self.assertNotIn("receive notifications are not in the app yet", src)

    def test_user_guide_denial_is_safe(self):
        src = read(USER_GUIDE)
        self.assertIn("the wallet itself is", src)


if __name__ == "__main__":
    unittest.main()
