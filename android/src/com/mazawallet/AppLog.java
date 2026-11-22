package com.mazawallet;

import android.util.Log;

import com.mazawallet.crypto.LogRing;

import java.util.List;

/**
 * M24: app console facade. STATUS-ONLY lines; every line is mirrored to
 * logcat (tag "MAZA") AND kept in a bounded ring shown on the Diagnostics
 * screen (Settings entry) with copy-to-clipboard. This class is the ONLY
 * android.util.Log sink in the app (M25 simplify pass: everything else
 * goes through here so the secret scan + LogRing.scrub cover all lines).
 *
 * <p>NEVER compose a secret value into an event string (bench token, PIN,
 * mnemonic, signed hex, Authorization header). The single HTTP choke point
 * (Api.http) logs method + normalized path + status + duration; no
 * headers, no bodies. LogRing.scrub truncates denylisted lines as
 * defense-in-depth.
 */
public final class AppLog {

    public static final String TAG = "MAZA";
    private static final LogRing RING = new LogRing();

    private AppLog() {
    }

    public static void i(String event) {
        Log.i(TAG, RING.add(event));
    }

    public static void w(String event) {
        Log.w(TAG, RING.add(event));
    }

    public static void d(String event) {
        Log.d(TAG, RING.add(event));
    }

    /** Retained lines, oldest first - one locked read for screen + count. */
    public static List<String> snapshot() {
        return RING.snapshot();
    }

    /** Max retained events (the facade owns the ring bound, not the UI). */
    public static int capacity() {
        return RING.capacity();
    }
}
