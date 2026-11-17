package com.mazawallet;

import android.hardware.biometrics.BiometricPrompt;

/**
 * S-2b-ii biometric prompt callback. Deliberately a TOP-LEVEL class: d8
 * 8.2.2-dev NPEs while dexing any NESTED class whose direct supertype is a
 * platform class (bisected 2026-11-17: a named inner class extending
 * BiometricPrompt.AuthenticationCallback and one implementing
 * DialogInterface.OnClickListener both crash d8 with "Cannot invoke
 * String.length() because <parameter1> is null", while a top-level
 * subclass of the same callback dexes clean - the skill's anonymous-class
 * d8 note was one instance of this broader nested-class rule).
 *
 * The callback is dumb plumbing: it resets the prompt bookkeeping and
 * forwards to MainActivity's package-private handlers, which own the
 * policy outcome (BiometricPolicy mapping, PinGuard fail-closed seam, the
 * shared completeUnlock landing). One instance per authenticate() call -
 * nothing here outlives the activity it points at.
 *
 * onAuthenticationFailed (biometric presented but NO match) is deliberately
 * NOT overridden: the platform keeps the prompt up and lets the user retry
 * within the same prompt session, and the device manages its own failure
 * accounting (D12: such attempts must not touch the PIN streak either -
 * the default behavior does exactly that).
 */
class PromptCb extends BiometricPrompt.AuthenticationCallback {

    private final MainActivity act;

    PromptCb(MainActivity act) {
        this.act = act;
    }

    @Override
    public void onAuthenticationSucceeded(BiometricPrompt.AuthenticationResult result) {
        act.biometricPromptFinished();
    }

    @Override
    public void onAuthenticationError(int errorCode, CharSequence errString) {
        act.biometricPromptFailed(errorCode);
    }
}
