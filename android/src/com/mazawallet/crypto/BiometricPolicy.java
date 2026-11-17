package com.mazawallet.crypto;

/**
 * Decision table for the S-2b-ii biometric unlock on MainActivity's PIN
 * cover. Pure Java (no Android imports) so the desktop selftest drives
 * every row BEHAVIORALLY: crypto/SelfTest.java biometricPolicyChecks()
 * evaluates the offer decision across its three inputs and maps every
 * platform error code the prompt can report.
 *
 * Ownership contract: MainActivity owns ALL platform interaction (SDK tier
 * probe, BiometricManager/FingerprintManager state, prompt construction,
 * cancellation) and feeds this class plain booleans/codes. The PIN pad is
 * ALWAYS the fallback: every outcome here leaves the cover up with the PIN
 * path intact - biometric success is the only path that removes it, and it
 * goes through PinGuard.unlockViaBiometric() (fail-closed on a corrupt
 * verifier store) so the platform can never open a gate the store cannot
 * coherently arm.
 *
 * Error-code policy (D12): biometric failures NEVER advance the PIN
 * wrong-attempt streak - the device throttles biometric attempts itself
 * (ERROR_LOCKOUT family), and the PIN backoff exists to slow a PIN
 * brute-force, not a fingerprint probe. User-initiated cancellations
 * (ERROR_USER_CANCELED / ERROR_NEGATIVE_BUTTON / ERROR_CANCELED) and
 * sensor/process errors are HOLD: the cover stays exactly as it was. A
 * lockout is LOCKED_OUT so the shell can stop re-offering into a dead
 * window for the rest of the session.
 */
public final class BiometricPolicy {

    /** Minimum API tier for OFFERING biometric unlock: 29, because the
     *  capability probe (android.hardware.biometrics.BiometricManager)
     *  is an API-29 class. API 28 devices (BlueStacks Pie64 included)
     *  get the graceful PIN-only path: BiometricPrompt exists there but
     *  capability can only be probed via FingerprintManager, which would
     *  need a second manifest permission (USE_FINGERPRINT) for one tier. */
    public static final int MIN_API = 29;

    /** Platform error codes, mirrored from android.hardware.biometrics.
     *  BiometricPrompt (values javap-verified against the android-34
     *  android.jar - never retype these from memory). This class stays free
     *  of any android dependency so the desktop selftest can run it. */
    public static final int ERR_HW_UNAVAILABLE = 1;
    public static final int ERR_UNABLE_TO_PROCESS = 2;
    public static final int ERR_TIMEOUT = 3;
    public static final int ERR_NO_SPACE = 4;
    public static final int ERR_CANCELED = 5;
    public static final int ERR_LOCKOUT = 7;
    public static final int ERR_VENDOR = 8;
    public static final int ERR_LOCKOUT_PERMANENT = 9;
    public static final int ERR_USER_CANCELED = 10;
    public static final int ERR_NO_BIOMETRICS = 11;
    public static final int ERR_HW_NOT_PRESENT = 12;
    public static final int ERR_NEGATIVE_BUTTON = 13;

    /** prompt-outcome outcomes (int constants: no enums - the d8 dev build
     *  NPEs on nested enum classes, verified live during S-2a). */
    public static final int HOLD = 0;       // cover unchanged, PIN path intact
    public static final int LOCKED_OUT = 1; // shell stops offering this session

    private BiometricPolicy() { }

    /**
     * Whether the lock cover may show the biometric path. All three inputs
     * are required: below MIN_API there is no probeable platform support;
     * a not-ready device (no hardware / nothing enrolled / sensor busy)
     * falls back silently; a CORRUPT verifier store is PIN-pad-only
     * fail-closed (PinGuard verifierState - the store can never silently
     * disable the gate, so it cannot delegate it either).
     *
     * @param apiAtLeastMin Build.VERSION.SDK_INT >= MIN_API, computed by the shell
     * @param biometricReady fresh platform probe (HW present + enrolled + usable)
     * @param verifierHealthy true when the PIN verifier store is VALID (not corrupt)
     */
    public static boolean offer(boolean apiAtLeastMin, boolean biometricReady,
                                boolean verifierHealthy) {
        return apiAtLeastMin && biometricReady && verifierHealthy;
    }

    /**
     * Map a platform onAuthenticationError code to a shell outcome.
     * HOLD covers everything except the lockout family: the cover stays,
     * the streak is untouched, and the next cover show re-probes the
     * platform (transient sensor states recover on their own).
     *
     * @param errorCode the code BiometricPrompt reported
     * @return HOLD or LOCKED_OUT (BiometricPolicy.ERR_LOCKOUT family)
     */
    public static int outcome(int errorCode) {
        if (errorCode == ERR_LOCKOUT || errorCode == ERR_LOCKOUT_PERMANENT) {
            return LOCKED_OUT;
        }
        return HOLD;
    }
}
