package com.mazawallet.crypto;

/**
 * Decision table for SettingsActivity's foreground lock enforcement
 * (r3 judge): given the verifier-store state and the live session's gate
 * decision, decide whether the settings screen must close.
 *
 * Pure Java (no Android imports) so the desktop selftest exercises every
 * row BEHAVIORALLY: crypto/SelfTest.java settingsResumeGateChecks() drives
 * this decision with the REAL LockPolicy as the live session across the
 * four judge scenarios - foreground expiry, touch-refreshed activity,
 * background/resume expiry, and task restoration without a live session.
 *
 * Ownership/lifecycle contract (r3/r4 judge rounds): MainActivity.sActiveGuard
 * is the ONE authoritative session guard. It is published in onCreate, nulled
 * in onDestroy, and SettingsActivity reads it on resume (applying the
 * background-duration lock FIRST, then clearing the bracket via
 * onForegroundChildResumed), on a 10s foreground tick, and forwards user
 * interaction to it; the child's onPause re-engages the bracket via
 * onBackground. A SettingsActivity restored WITHOUT a live guard (process-
 * death restoration path) is fail-closed whenever a PIN verifier exists: the
 * screen finishes and the user re-enters through the gated WALLET tab,
 * because without the live guard there is no way to know the session was
 * unlocked.
 */
public final class SettingsResumePolicy {
    public static final int STAY = 0;
    public static final int CLOSE = 1;

    private SettingsResumePolicy() { }

    /**
     * @param verifierSet     true when a PIN verifier exists in the store
     *                        (the fail-closed anchor for missing live state)
     * @param haveLiveSession true when MainActivity's sActiveGuard is
     *                        available right now
     * @param liveGateNeeded  the live guard's gateNeeded() when
     *                        haveLiveSession, otherwise ignored
     * @return CLOSE when the settings screen must finish() immediately
     */
    public static int evaluate(boolean verifierSet, boolean haveLiveSession,
                               boolean liveGateNeeded) {
        if (haveLiveSession) {
            return liveGateNeeded ? CLOSE : STAY;
        }
        // No live session: fail-closed for PIN-protected wallets; a
        // PIN-less wallet has no gate to enforce (same as pre-PIN builds).
        return verifierSet ? CLOSE : STAY;
    }
}
