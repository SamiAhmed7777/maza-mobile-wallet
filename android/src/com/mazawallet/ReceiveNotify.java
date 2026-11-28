package com.mazawallet;

import android.app.Activity;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.content.Context;
import android.content.pm.PackageManager;
import android.os.Build;

import com.mazawallet.crypto.NotifyPolicy;
import com.mazawallet.crypto.SendEchoTracker;

/**
 * M14: posts the local "MAZA received" notification. APP-ALIVE SCOPE
 * (DECISIONS.md D16): this rides the existing 15-second poll, which keeps
 * running while the app is locked and while it is backgrounded (the poll
 * stops only on destroy/disconnect). There is NO push path - notifications
 * never fire once the process is gone. Amounts appear in the notification
 * text by design; the lock-screen exposure is documented in the user guide.
 *
 * Top-level class, no platform supertype (the d8 nested-class rule). The
 * pure decisions live in crypto/NotifyPolicy (desktop-selftested); this
 * class is the thin Android shell.
 */
public final class ReceiveNotify {
    /** Distinct ids so a bench receive and a seed receive never overwrite
     *  each other's notification. */
    private static final int ID_BENCH = 1;
    private static final int ID_WALLET = 2;

    /** Runtime permission request code (MainActivity-scoped, unused by others). */
    private static final int REQ_POST_NOTIFICATIONS = 3001;

    private ReceiveNotify() {}

    /** Creates the notification channel (API 26+; idempotent no-op below it
     *  or when the channel already exists). Call once per session. */
    public static void ensureChannel(Context ctx) {
        if (!NotifyPolicy.channelNeeded(Build.VERSION.SDK_INT)) {
            return;
        }
        NotificationManager nm = notificationManager(ctx);
        if (nm == null || nm.getNotificationChannel(NotifyPolicy.CHANNEL_ID) != null) {
            return;
        }
        NotificationChannel ch = new NotificationChannel(NotifyPolicy.CHANNEL_ID,
                ctx.getString(R.string.notify_channel_name),
                NotificationManager.IMPORTANCE_DEFAULT);
        ch.setDescription(ctx.getString(R.string.notify_channel_desc));
        nm.createNotificationChannel(ch);
    }

    /** One bench-account sample: fires on a strict increase over the last
     *  sample, EXCEPT the wallet's own send-settle echo (M32: echo is the
     *  tracker's verdict); returns the satoshi value to store as the next
     *  last-seen (the previous value unchanged when the balance is
     *  malformed - a bad sample must neither fire nor reset the
     *  continuity). The tracker is REQUIRED (both call sites wire one). */
    public static Long observeBench(Context ctx, Long prev, double balanceMaza,
                                    SendEchoTracker echo) {
        return observe(ctx, prev, balanceMaza, ID_BENCH,
                ctx.getString(R.string.notify_src_bench), echo);
    }

    /** One self-custody watch-set sample (same contract as observeBench). */
    public static Long observeWallet(Context ctx, Long prev, double balanceMaza,
                                     SendEchoTracker echo) {
        return observe(ctx, prev, balanceMaza, ID_WALLET,
                ctx.getString(R.string.notify_src_wallet), echo);
    }

    /** Asks for the Android 13+ POST_NOTIFICATIONS grant once per session.
     *  Returns the new asked-state (always true after the first call, so a
     *  denial is never re-prompted mid-session). Denied = no notifications;
     *  the wallet itself is unaffected. */
    public static boolean requestIfNeeded(Activity act, boolean alreadyAsked) {
        if (alreadyAsked) {
            return true;
        }
        boolean granted = granted(act);
        if (NotifyPolicy.runtimeRequestNeeded(Build.VERSION.SDK_INT, granted)) {
            act.requestPermissions(
                    new String[]{android.Manifest.permission.POST_NOTIFICATIONS},
                    REQ_POST_NOTIFICATIONS);
        }
        return true;
    }

    // ------------------------------------------------------------------

    private static Long observe(Context ctx, Long prev, double balanceMaza,
                                int id, String source, SendEchoTracker echo) {
        long cur;
        try {
            cur = NotifyPolicy.toSats(balanceMaza);
        } catch (IllegalArgumentException e) {
            return prev; // malformed sample: no fire, no continuity reset
        }
        // M32: the tracker owns the fire decision (own-send settle echo
        // suppressed; delta -1 = never announce). Malformed input never
        // reaches it (toSats threw above; toSats output is >= 0).
        long delta = echo.onSample(prev, cur, System.currentTimeMillis());
        if (delta >= 0 && enabled(ctx)) {
            fire(ctx, delta, id, source);
        }
        return Long.valueOf(cur);
    }

    private static void fire(Context ctx, long deltaSats, int id, String source) {
        NotificationManager nm = notificationManager(ctx);
        if (nm == null) {
            return;
        }
        Notification.Builder b = NotifyPolicy.channelNeeded(Build.VERSION.SDK_INT)
                ? new Notification.Builder(ctx, NotifyPolicy.CHANNEL_ID)
                : new Notification.Builder(ctx);
        b.setSmallIcon(R.drawable.ic_notify) // flat monochrome glyph: the
            // shade's tint pipeline renders launcher mipmaps poorly (D16)
                .setContentTitle(ctx.getString(R.string.notify_title))
                .setContentText("+" + fmtMaza(deltaSats) + " MAZA - " + source)
                .setAutoCancel(true);
        nm.notify(id, b.build());
    }

    /** areNotificationsEnabled() covers both the pre-13 master switch and
     *  the 13+ runtime grant in one call (API 24+, our minSdk). */
    private static boolean enabled(Context ctx) {
        NotificationManager nm = notificationManager(ctx);
        return nm != null && nm.areNotificationsEnabled();
    }

    private static boolean granted(Context ctx) {
        if (Build.VERSION.SDK_INT < NotifyPolicy.RUNTIME_PERM_API) {
            return true; // pre-13: no runtime grant exists
        }
        return ctx.checkSelfPermission(
                android.Manifest.permission.POST_NOTIFICATIONS)
                == PackageManager.PERMISSION_GRANTED;
    }

    private static NotificationManager notificationManager(Context ctx) {
        return (NotificationManager) ctx.getSystemService(Context.NOTIFICATION_SERVICE);
    }

    /** Fixed 8dp satoshi rendering for the notification text. */
    private static String fmtMaza(long sats) {
        long whole = sats / NotifyPolicy.COIN;
        long frac = sats % NotifyPolicy.COIN;
        return whole + "." + String.format(java.util.Locale.US, "%08d", frac);
    }
}
