#!/usr/bin/env python3
"""Wiring contract for SettingsActivity's foreground lock enforcement.

The lock-state MATH and the decision table are covered BEHAVIORALLY in
crypto/SelfTest.java settingsResumeGateChecks() (real LockPolicy driven
through SettingsResumePolicy.evaluate across foreground expiry, touch
activity, background/resume, and restoration scenarios).

This file pins the thin ANDROID WIRING that cannot run on the desktop JVM:
that SettingsActivity actually calls the decision (on resume, on a
foreground tick, and on user interaction), that it consults the LIVE
session guard (MainActivity.sActiveGuard) rather than a freshly constructed
per-instance guard (which starts LOCKED by design), and that SelfTest
carries the behavioral proof. Kept deliberately small: everything that CAN
be tested by execution is tested by execution in SelfTest.
"""
import os
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN = os.path.join(REPO, "android", "src", "com", "mazawallet", "MainActivity.java")
SETTINGS = os.path.join(REPO, "android", "src", "com", "mazawallet", "SettingsActivity.java")
SELFTEST = os.path.join(REPO, "android", "src", "com", "mazawallet", "crypto", "SelfTest.java")
POLICY = os.path.join(REPO, "android", "src", "com", "mazawallet", "crypto", "SettingsResumePolicy.java")


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class SettingsForegroundLockWiring(unittest.TestCase):
    def test_main_activity_publishes_and_clears_the_live_session_guard(self):
        src = read(MAIN)
        self.assertIn("static PinGuard sActiveGuard", src)
        self.assertIn("sActiveGuard = pinGuard;", src)
        self.assertIn("if (sActiveGuard == pinGuard) sActiveGuard = null;", src,
                      "onDestroy must null the static guard")

    def test_settings_enforces_the_gate_across_the_foreground_lifetime(self):
        src = read(SETTINGS)
        self.assertIn("SettingsResumePolicy.evaluate(", src,
                      "the decision must go through the pure, behaviorally-tested policy")
        self.assertIn("MainActivity.sActiveGuard", src)
        self.assertIn("ui.postDelayed(lockTick, 10_000L);", src,
                      "a foreground tick must enforce the gate between resumes")
        self.assertIn("ui.removeCallbacks(lockTick);", src,
                      "the tick must stop when the screen pauses")
        self.assertIn("public void onUserInteraction()", src,
                      "settings touches must reach the live session")
        self.assertIn("session.onActivity();", src,
                      "touch forwarding must push the live deadline")

    def test_no_local_guard_in_the_resume_decision(self):
        src = read(SETTINGS)
        i = src.find("private boolean enforceResumeGate()")
        self.assertTrue(i >= 0, "enforceResumeGate() must exist")
        block = src[i:src.find("private static void", i)] if "private static void" in src[i:] else src[i:]
        self.assertNotIn("pinGuard.gateNeeded()", block,
                         "a fresh per-instance guard starts LOCKED by design; "
                         "the enforcement must use the live session guard")

    def test_settings_brackets_the_background_across_the_child(self):
        src = read(SETTINGS)
        self.assertIn("session.onResumeLocked();", src,
                      "the engaged device-out-of-sight bracket must be applied first")
        self.assertIn("session.onForegroundChildResumed();", src,
                      "the bracket must clear for ongoing in-app foreground use")
        # Order is load-bearing (r5 polish): the duration lock must be
        # applied BEFORE the bracket is cleared.
        i_apply = src.find("session.onResumeLocked();")
        i_clear = src.find("session.onForegroundChildResumed();")
        self.assertTrue(0 <= i_apply < i_clear,
                        "onResumeLocked() must precede onForegroundChildResumed()")
        j = src.find("protected void onPause()")
        k = src.find("super.onPause();", j)
        pause_block = src[j:k] if 0 < j < k else ""
        self.assertIn("session.onBackground();", pause_block,
                      "the child's pause must re-engage the bracket")

    def test_selftest_carries_the_behavioral_proof(self):
        src = read(SELFTEST)
        self.assertIn("settingsResumeGateChecks", src)
        for scenario in ("foreground expiry closes",
                         "touch activity keeps the screen open",
                         "background/resume after expiry closes",
                         "restored without a live guard + verifier -> fail-closed CLOSE",
                         "active settings use then back-nav stays open",
                         "HOME from settings past the window locks on return"):
            self.assertIn(scenario, src, "behavioral scenario missing from SelfTest")

    def test_decision_class_is_pure_java(self):
        src = read(POLICY)
        self.assertNotIn("import android", src,
                         "SettingsResumePolicy must stay desktop-testable (no Android imports)")


if __name__ == "__main__":
    unittest.main()
