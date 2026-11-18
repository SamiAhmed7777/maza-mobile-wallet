package com.mazawallet.crypto;

/**
 * M14: local receive-notification decision table. Pure Java, no Android
 * imports (desktop-selftested; the wiring that uses it is pinned by
 * tests/test_notify_wiring.py and the calling classes stay thin).
 *
 * Scope honesty (DECISIONS.md D16): the app has NO push path. A receive
 * notification fires only while the app process is alive, riding the
 * existing 15-second poll (which keeps running while the app is locked
 * and while it is backgrounded). The last-seen balance is memory-only per
 * session: the first sample of a session NEVER fires, so unlocking or
 * reconnecting does not re-announce an old balance. Only a STRICT increase
 * between two consecutive samples is a receive; equal balances and
 * decreases (sends, fees) never notify.
 */
public final class NotifyPolicy {
    /** Satoshis per MAZA (1e8). */
    public static final long COIN = 100000000L;

    /** Notification channel id (the app's single notification channel). */
    public static final String CHANNEL_ID = "incoming_maza";

    /** Android 13 (API 33) gates notifications behind a runtime grant. */
    public static final int RUNTIME_PERM_API = 33;

    /** NotificationChannel exists from Android 8.0 (API 26). */
    public static final int CHANNEL_API = 26;

    private NotifyPolicy() {}

    /** MAZA (8dp double) to satoshi, half-up rounding. Loud on negative or
     *  non-finite input (a NaN balance must never silently compare). */
    public static long toSats(double maza) {
        if (!(maza >= 0)) { // false for negatives AND NaN
            throw new IllegalArgumentException("balance must be >= 0");
        }
        return Math.round(maza * (double) COIN);
    }

    /** A receive = a STRICT increase between two consecutive samples.
     *  {@code prevSats == null} is the session's first sample: never fires.
     *  The negative branches are defense-in-depth: ReceiveNotify.observe
     *  already guarantees non-negative input through toSats, but the
     *  policy stays loud if a future caller bypasses it. */
    public static boolean shouldFire(Long prevSats, long newSats) {
        if (prevSats == null) {
            return false;
        }
        if (prevSats.longValue() < 0) {
            throw new IllegalArgumentException("negative prev");
        }
        if (newSats < 0) {
            throw new IllegalArgumentException("negative new");
        }
        return newSats > prevSats.longValue();
    }

    /** True when the POST_NOTIFICATIONS runtime grant must be requested
     *  (Android 13+ and not yet granted; older APIs are pre-granted). */
    public static boolean runtimeRequestNeeded(int apiLevel, boolean granted) {
        if (apiLevel < 0) {
            throw new IllegalArgumentException("apiLevel");
        }
        return apiLevel >= RUNTIME_PERM_API && !granted;
    }

    /** True when a NotificationChannel must exist (API 26+); below it the
     *  legacy notification path needs no channel. */
    public static boolean channelNeeded(int apiLevel) {
        if (apiLevel < 0) {
            throw new IllegalArgumentException("apiLevel");
        }
        return apiLevel >= CHANNEL_API;
    }
}
