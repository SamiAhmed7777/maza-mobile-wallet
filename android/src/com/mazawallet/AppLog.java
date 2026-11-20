package com.mazawallet;

import android.util.Log;

import com.mazawallet.crypto.LogRing;

/**
 * M24: app console facade. STATUS-ONLY lines; every line is mirrored to
 * logcat (tag "MAZA") AND kept in a bounded ring shown on the Diagnostics
 * screen (Settings entry, PIN-gated) with copy-to-clipboard.
 *
 * <p>NEVER compose a secret value into an event string (bench token, PIN,
 * mnemonic, signed hex, Authorization header). The single HTTP choke point
 * (Api.http) logs method + path-only + status + duration; no headers, no
 * bodies. LogRing.scrub truncates denylisted lines as defense-in-depth.
 */
public final class AppLog {

    public static final String TAG = "MAZA";
    private static final LogRing RING = new LogRing(LogRing.DEFAULT_CAPACITY);

    private AppLog() {
    }

    public static void i(String event) {
        emit("i", event);
    }

    public static void w(String event) {
        emit("w", event);
    }

    public static void d(String event) {
        emit("d", event);
    }

    private static void emit(String level, String event) {
        String line = RING.add(event);
        if ("w".equals(level)) {
            Log.w(TAG, line);
        } else if ("d".equals(level)) {
            Log.d(TAG, line);
        } else {
            Log.i(TAG, line);
        }
    }

    /** Newest-last dump for the Diagnostics screen / clipboard. */
    public static String dump() {
        StringBuilder sb = new StringBuilder();
        for (String line : RING.snapshot()) {
            if (sb.length() > 0) {
                sb.append('\n');
            }
            sb.append(line);
        }
        return sb.toString();
    }

    public static int size() {
        return RING.size();
    }
}
