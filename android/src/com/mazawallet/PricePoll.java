package com.mazawallet;

/**
 * M26: how often the wallet asks the bench for a price, and what it
 * remembers between asks. One read per {@link #INTERVAL_MS}, riding the
 * screens' own 15 s polls - no timer, no wakelock, nothing to leak. The
 * bench refreshes its venue price every 60 s, so asking more often only
 * re-reads the same cached answer.
 *
 * <p>One gate is normally SHARED by every line that shows the price, so a
 * rebuilt or re-opened screen repaints from {@link #last()} instead of
 * asking again. A new session (unlock, another endpoint) calls
 * {@link #clear()}; an answer that was already in flight for the previous
 * session is dropped when it arrives, and again if the session ends
 * before it is painted ({@link #isCurrent}).
 *
 * <p>Every method is synchronized: the screens ask from their own worker
 * threads and repaint on the UI thread. No lock is ever held across I/O.
 *
 * <p>The bench's TTLs, stale window and maximum age live server-side
 * (walletbench/price.py). This class holds no opinion about prices.
 *
 * <p>PLATFORM ONLY (java.* alone): tests/test_price_wiring.py compiles this
 * on the desktop JVM and drives the real gate.
 */
public final class PricePoll {

    /** One price read per minute. An engineering choice, not an
     *  inherited coin parameter (MazaCore has no price feed). */
    public static final long INTERVAL_MS = 60_000L;

    /** What {@link #due} returns when no read is due. */
    public static final long NOT_DUE = -1L;

    private long lastAskMs = -INTERVAL_MS;
    private boolean unsupported;
    /** Bumped by clear(): every answer carries the session it was asked in. */
    private long session;
    private PriceLine.Quote last;

    /** Take this minute's slot. Returns a ticket to hand back with the
     *  answer, or NOT_DUE. Asking consumes the slot, so a failed read also
     *  waits a minute: the bench's stale flag is what tells the user a price
     *  is old, not a tighter poll. */
    public synchronized long due(long nowMs) {
        if (unsupported || nowMs - lastAskMs < INTERVAL_MS) return NOT_DUE;
        lastAskMs = nowMs;
        return session;
    }

    /** The bench answered (null: "no source right now"). Returns false
     *  when the answer belongs to a session that has since been cleared. */
    public synchronized boolean record(long ticket, PriceLine.Quote quote) {
        if (ticket != session) return false;
        last = quote;
        return true;
    }

    /** The quote currently on screen (null: the line is hidden). */
    public synchronized PriceLine.Quote last() {
        return last;
    }

    /** The endpoint has no /api/price route (an older bench): stop asking
     *  for the rest of the session instead of logging a 404 every minute.
     *  Ignored when that 404 came from a session that has since ended. */
    public synchronized void retire(long ticket) {
        if (ticket == session) unsupported = true;
    }

    /** A new session (unlock, another endpoint): forget the previous
     *  endpoint's quote and ask again right away. A repaint must NOT call
     *  this - it reads last() and keeps the line. */
    public synchronized void clear() {
        unsupported = false;
        lastAskMs = -INTERVAL_MS;
        last = null;
        session++;
    }

    /** True while {@code ticket} is still the current session. The paint
     *  repeats this check on the UI thread: an answer can be recorded,
     *  the session end, and only then the paint run. clear() runs on that
     *  same thread, so the check and the paint cannot interleave. */
    public synchronized boolean isCurrent(long ticket) {
        return ticket == session;
    }
}
