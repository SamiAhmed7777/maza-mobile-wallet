#!/usr/bin/env python3
"""Wiring contract for the S-2b-ii biometric unlock.

The decision MATH (offer table, error-code mapping, acceptUnlock
accepted-auth semantics) is covered BEHAVIORALLY in crypto/SelfTest.java
biometricPolicyChecks() with the real LockPolicy on a fake clock.

This file pins the thin ANDROID WIRING that cannot run on the desktop JVM:
that MainActivity consults the pure policy at every cover show, guards the
platform prompt behind the API tier, routes biometric success through the
PinGuard fail-closed seam and the SAME unlock landing as an accepted PIN,
stops offering after a lockout, cancels the prompt on teardown, and that
the manifest carries the permission platform BiometricPrompt.authenticate()
requires. Kept deliberately small: everything that CAN be tested by
execution is tested by execution in SelfTest.
"""
import os
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN = os.path.join(REPO, "android", "src", "com", "mazawallet", "MainActivity.java")
GUARD = os.path.join(REPO, "android", "src", "com", "mazawallet", "PinGuard.java")
POLICY = os.path.join(REPO, "android", "src", "com", "mazawallet",
                      "crypto", "BiometricPolicy.java")
LOCKPOLICY = os.path.join(REPO, "android", "src", "com", "mazawallet",
                          "crypto", "LockPolicy.java")
SELFTEST = os.path.join(REPO, "android", "src", "com", "mazawallet",
                        "crypto", "SelfTest.java")
MANIFEST = os.path.join(REPO, "android", "AndroidManifest.xml")
STRINGS = os.path.join(REPO, "android", "res", "values", "strings.xml")


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class BiometricPolicyPurity(unittest.TestCase):
    def test_policy_is_pure_java(self):
        """The desktop selftest compiles/claims this package: no android.*."""
        src = read(POLICY)
        imports = [ln for ln in src.splitlines()
                   if ln.strip().startswith("import ")]
        self.assertFalse([ln for ln in imports if "android" in ln],
                         "BiometricPolicy must stay pure Java (desktop JVM): "
                         "android imports found: %r" % imports)
        self.assertIn("class BiometricPolicy", src)
        self.assertIn("public static final int MIN_API = 29;", src,
                      "BiometricManager (the capability probe) is an API-29 class")
        self.assertIn("public static boolean offer(", src)
        self.assertIn("public static int outcome(int errorCode)", src)
        self.assertIn("ERR_LOCKOUT_PERMANENT = 9;", src,
                      "mirrored platform codes must keep their verified values")
        self.assertIn("ERR_USER_CANCELED = 10;", src)
        self.assertIn("ERR_NEGATIVE_BUTTON = 13;", src)


class AcceptUnlockContract(unittest.TestCase):
    def test_lockpolicy_has_the_accepted_auth_path(self):
        src = read(LOCKPOLICY)
        self.assertIn("public void acceptUnlock(long now)", src)
        self.assertIn("wrongStreak = 0;", src)
        self.assertIn("backoffUntil = 0;", src)

    def test_pinguard_biometric_seam_fails_closed(self):
        src = read(GUARD)
        i = src.find("public synchronized boolean unlockViaBiometric()")
        self.assertTrue(i >= 0, "unlockViaBiometric() must exist")
        block = src[i:src.find("private static long elapsedNow", i)]
        self.assertIn("verifierState() != STATE_VALID", block,
                      "a CORRUPT store must refuse the biometric unlock")
        self.assertIn("policy.acceptUnlock(", block)
        self.assertIn("public boolean biometricUnlockAllowed()", src)
        self.assertIn("verifierState() == STATE_VALID", src)


class MainActivityBiometricWiring(unittest.TestCase):
    def test_cover_offer_goes_through_the_pure_policy(self):
        src = read(MAIN)
        i = src.find("private void showLock()")
        self.assertTrue(i >= 0)
        block = src[i:src.find("lockOverlay.setVisibility(View.VISIBLE);", i)]
        self.assertIn("BiometricPolicy.offer(", block,
                      "the offer decision must go through the tested policy")
        self.assertIn("Build.VERSION.SDK_INT >= BiometricPolicy.MIN_API", block)
        self.assertIn("biometricReadyNow()", block,
                      "a FRESH platform probe per cover show")
        self.assertIn("pinGuard.biometricUnlockAllowed()", block)
        self.assertIn("!biometricSessionOff", block,
                      "a locked-out sensor must not be re-offered")

    def test_prompt_is_tier_guarded_and_lands_on_the_shared_unlock(self):
        src = read(MAIN)
        i = src.find("private void startBiometricPrompt()")
        self.assertTrue(i >= 0, "startBiometricPrompt() must exist")
        block = src[i:src.find("void biometricPromptFinished()", i)]
        self.assertIn("Build.VERSION.SDK_INT < BiometricPolicy.MIN_API", block,
                      "the prompt must be tier-guarded")
        self.assertIn("cancelBiometricPrompt(); // never two live prompts", block)
        self.assertIn("new BiometricPrompt.Builder(", block)
        self.assertIn("setNegativeButton(", block)
        self.assertIn("new PromptCb(this)", block,
                      "the callback must be the TOP-LEVEL PromptCb (d8 rule)")
        self.assertIn("private void onBiometricSuccessUi()", src)
        j = src.find("private void onBiometricSuccessUi()")
        succ = src[j:src.find("private void onBiometricErrorUi()", j)]
        self.assertIn("pinGuard.unlockViaBiometric()", succ,
                      "success must pass the fail-closed PinGuard seam")
        self.assertIn("completeUnlock();", succ,
                      "success must land on the SAME unlock path as an accepted PIN")
        self.assertIn("showLock();", succ, "fail-closed: the cover stays up")
        k = src.find("private void onBiometricErrorUi()")
        err = src[k:src.find("/** Cancel any live prompt", k)]
        self.assertIn("BiometricPolicy.outcome(pendingBiometricError)", err,
                      "errors must map through the tested policy")
        self.assertIn("biometricSessionOff = true;", err,
                      "a lockout must stop the session offer")

    def test_prompt_cb_is_top_level(self):
        """d8 8.2.2-dev NPEs while dexing any NESTED class whose direct
        supertype is a platform class (bisected 2026-11-17: named inner
        extends/implements both crash; a top-level subclass of the same
        callback dexes clean). Pin the shape so it cannot regress."""
        src = read(os.path.join(REPO, "android", "src", "com", "mazawallet",
                                "PromptCb.java"))
        self.assertIn("class PromptCb extends "
                      "BiometricPrompt.AuthenticationCallback", src)
        self.assertNotIn("class MainActivity", src)
        self.assertIn("act.biometricPromptFinished()", src)
        self.assertIn("act.biometricPromptFailed(errorCode)", src)
        main_src = read(MAIN)
        self.assertNotIn("private class PromptCb", main_src,
                         "the callback must stay TOP-LEVEL (d8 nested-class rule)")
        self.assertNotIn("implements DialogInterface.OnClickListener {",
                         main_src)

    def test_pin_path_and_biometric_share_one_unlock_landing(self):
        src = read(MAIN)
        self.assertIn("private void completeUnlock()", src)
        self.assertIn("if (r == LockPolicy.ACCEPTED) {\n                    completeUnlock();",
                      src, "the accepted-PIN branch must use completeUnlock()")
        self.assertIn("private void cancelBiometricPrompt()", src)
        self.assertIn("cancelBiometricPrompt(); // S-2b-ii: no prompt survives this activity",
                      src, "onDestroy must cancel a live prompt")
        self.assertIn("private boolean biometricReadyNow()", src)
        self.assertIn("biometricBtn", src)

    def test_manifest_declares_exactly_internet_plus_use_biometric(self):
        """platform BiometricPrompt.authenticate() requires USE_BIOMETRIC
        (developer.android.com BiometricPrompt reference, javap-verified
        constants); it is a normal-level permission. M8b added CAMERA (the
        SEND-tab QR scan surface, runtime-requested). M14 added
        POST_NOTIFICATIONS (the local receive notifications, runtime-
        requested on Android 13+). Nothing else may ride in - the beta
        battery asserts this exact set."""
        src = read(MANIFEST)
        self.assertIn('<uses-permission android:name="android.permission.INTERNET" />', src)
        self.assertIn('<uses-permission android:name="android.permission.USE_BIOMETRIC" />', src)
        self.assertIn('<uses-permission android:name="android.permission.CAMERA" />', src)
        self.assertIn('<uses-permission android:name="android.permission.POST_NOTIFICATIONS" />',
                      src)
        perms = [ln.strip() for ln in src.splitlines()
                 if "<uses-permission" in ln]
        self.assertEqual(len(perms), 4,
                         "exactly INTERNET + USE_BIOMETRIC + CAMERA + POST_NOTIFICATIONS")

    def test_strings_carry_the_biometric_copy(self):
        src = read(STRINGS)
        for key in ("biometric_title", "biometric_subtitle",
                    "biometric_use_pin", "biometric_unlock_button"):
            self.assertIn('name="%s"' % key, src)

    def test_selftest_carries_the_behavioral_scenarios(self):
        src = read(SELFTEST)
        self.assertIn("biometricPolicyChecks()", src)
        for scenario in ("biometric-s1: five wrong PINs open the backoff window",
                         "biometric-s1: accepted auth clears the backoff window",
                         "biometric-s2: accepted auth opens the locked gate",
                         "biometric-s3: accepted auth on an open gate stays open"):
            self.assertIn(scenario, src)


if __name__ == "__main__":
    unittest.main()
