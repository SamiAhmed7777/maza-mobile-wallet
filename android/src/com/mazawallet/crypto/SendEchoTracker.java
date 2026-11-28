package com.mazawallet.crypto;

/**
 * M32: keep the wallet's own send-settle echo out of the receive
 * notifications. Pure Java, no Android imports (desktop-selftested;
 * the wiring that uses it is pinned by tests/test_notify_wiring.py
 * and the calling classes stay thin).
 *
 * THE DEFECT (found on device 2026-11-27, 3 of 3 sends): a send spends
 * the largest coin whole and pays the change to a new address. The
 * sampled balance (the confirmed-unspent sum) reads ~0 until the change
 * confirms, then settles BELOW the pre-send baseline - a STRICT increase
 * between two consecutive samples, so NotifyPolicy.shouldFire announced
 * the account's own change as "MAZA received" (captured: "+46.49977740
 * MAZA - bench account" right after a send; nothing was received).
 *
 * THE FIX SHAPE ("skipping sends the account made itself"): when the app
 * itself completes a send it records a settle ceiling - the balance the
 * account can reach by settling its own change cannot exceed the last
 * sampled balance minus what the send moved out. While the settle window
 * is open:
 *   - a sample at or below the ceiling is the echo (or the unconfirmed
 *     dip): NEVER announced; the sample is still stored, so continuity
 *     continues and a later window expiry lands silently;
 *   - a sample ABOVE the ceiling carries external money: only the part
 *     above max(stored sample, ceiling) is announced (a receive landing
 *     while change settles still announces, with the echo excluded);
 *   - the session's first sample still never fires (the NotifyPolicy
 *     first-sample rule is preserved verbatim).
 * After the window the strict-increase rule resumes unchanged.
 *
 * SCOPE HONESTY (DECISIONS.md D21): this covers sends the APP initiated
 * (the bench /api/send path and the self-custody /api/broadcast path).
 * Node-side money movement the app did not initiate (operator funding
 * sweeps, M20 reconciliation) is OUT of scope: the app has no signal to
 * tell it from a receive.
 *
 * The 30-minute window is an ENGINEERING CHOICE (D21): it must cover the
 * unconfirmed-to-confirmed settle of the change output (minutes on this
 * chain), which is not a consensus property. A second send while a window
 * is open lowers the ceiling by what the second send moved out and re-arms
 * the window (each send only ever reduces the reachable settled balance,
 * so the arithmetic composes even when samples in between read the dip).
 *
 * The tracker survives a reconnect on purpose: a settle still in flight
 * when the session drops must not announce after reconnect (the stored
 * sample is null then, so the first sample after reconnect cannot fire
 * anyway, and the window bounds the state). The SEED tracker is the
 * exception: a fresh/imported seed resets it, because the old wallet's
 * ceiling says nothing about the new wallet's money.
 */
public final class SendEchoTracker {
    /** Settle window: 30 minutes (D21, engineering choice). */
    public static final long WINDOW_MS = 30L * 60L * 1000L;

    private Long ceilingSats;   // null = no settle pending
    private long windowEndMs;

    /** Call ONCE when the app completed a send that moved sentSats out of
     *  the sampled account. lastSampleSats is the last balance the poll
     *  stored; null (never sampled) REFUSES to arm and returns false - a
     *  session with no sample has no sane ceiling, and missing the
     *  suppression degrades to the previous behavior, never to a wrong
     *  announce. Loud on a non-positive amount or a negative sample.
     *  Thread-safe: the send completes on a worker thread, the poll
     *  samples on the UI thread. */
    public synchronized boolean onSend(Long lastSampleSats, long sentSats,
                                       long nowMs) {
        if (sentSats <= 0) {
            throw new IllegalArgumentException("sentSats must be > 0");
        }
        if (lastSampleSats == null) {
            return false;
        }
        if (lastSampleSats.longValue() < 0) {
            throw new IllegalArgumentException("negative lastSampleSats");
        }
        long base = pending(nowMs)
                ? ceilingSats.longValue()
                : lastSampleSats.longValue();
        ceilingSats = Long.valueOf(base - sentSats);
        windowEndMs = nowMs + WINDOW_MS;
        return true;
    }

    /** One sampled balance. Returns the sat delta the notification layer
     *  may announce (>= 0), or -1 for NEVER announce (the echo, the
     *  unconfirmed dip, a decrease, or the session's first sample).
     *  prevSats is the stored sample; the caller stores newSats as the
     *  next sample either way, so expiry lands on an unchanged balance
     *  and cannot fire. Loud on negative input. Thread-safe. */
    public synchronized long onSample(Long prevSats, long newSats,
                                      long nowMs) {
        if (newSats < 0) {
            throw new IllegalArgumentException("negative newSats");
        }
        if (prevSats != null && prevSats.longValue() < 0) {
            throw new IllegalArgumentException("negative prevSats");
        }
        boolean pending = pending(nowMs);
        if (!pending) {
            ceilingSats = null;
        }
        if (prevSats == null) {
            return -1L; // session's first sample: never fires
        }
        if (!pending) {
            // No settle pending: the NotifyPolicy rule verbatim (ONE
            // implementation of the strict-increase rule).
            return NotifyPolicy.shouldFire(prevSats, newSats)
                    ? newSats - prevSats.longValue() : -1L;
        }
        long ceiling = ceilingSats.longValue();
        if (newSats <= ceiling) {
            return -1L; // own settle echo, or the unconfirmed dip
        }
        long base = Math.max(prevSats.longValue(), ceiling);
        long excess = newSats - base;
        return excess > 0 ? excess : -1L;
    }

    /** True while a live (not yet expired) settle window is open. */
    public synchronized boolean pending(long nowMs) {
        return ceilingSats != null && nowMs <= windowEndMs;
    }

    /** Clears the pending settle state. The SEED wallet calls this when a
     *  fresh seed replaces the old one: the old wallet's ceiling says
     *  nothing about the new wallet's money. The bench tracker never
     *  resets (same account across sessions). */
    public synchronized void resetForNewSeed() {
        ceilingSats = null;
        windowEndMs = 0L;
    }
}
