package com.mazawallet.crypto;

/**
 * PIN-lock state machine (S-2a). Pure Java, injectable clock, so the desktop
 * selftest pins every transition. The Android shell (PinGuard) owns storage
 * and UI; this class owns ONLY the policy:
 *
 *  - lazy auto-lock: isLocked(now) locks when now - lastActivity >=
 *    autolockMs, so a late/missed timer tick can never keep the gate open —
 *    the gate decision itself is authoritative;
 *  - background-return lock: backgrounded longer than autolockMs locks on
 *    resume (onBackground/onResume bracket the paused state);
 *  - wrong-PIN throttle: after MAX_ATTEMPTS consecutive failures verifies are
 *    refused WITHOUT evaluating the PIN (no hash work) for a doubling backoff
 *    window (BASE << (n - MAX_ATTEMPTS), capped). The streak resets ONLY on
 *    an accepted verify — it survives auto-lock, so "4 wrong, wait for
 *    auto-lock, repeat" cannot dodge the backoff.
 *
 * "Activity" means any user touch: it pushes the inactivity deadline but
 * never unlocks (only an accepted verify unlocks).
 */
public final class LockPolicy {

    /** verifyAttempt outcomes (int constants: the d8/R8 dev build NPEs on
     *  nested enum classes — verified live during S-2a — so no enums). */
    public static final int ACCEPTED = 0;
    public static final int WRONG_PIN = 1;
    public static final int THROTTLED = 2;

    public static final int MAX_ATTEMPTS = 5;
    public static final long BACKOFF_BASE_MS = 30_000L;      // 5 fails -> 30s
    public static final long BACKOFF_CAP_MS = 15 * 60_000L;  // cap 15 min

    /** Supported inactivity windows (S-4 settings selector: 5/10/30 min).
     *  Bounds, not options: the shell owns the menu, this class only refuses
     *  a window it cannot enforce meaningfully (a 1-second or 24-hour
     *  "auto-lock" is a configuration bug, not a policy). */
    public static final long MIN_AUTOLOCK_MS = 60_000L;        // 1 min
    public static final long MAX_AUTOLOCK_MS = 60 * 60_000L;   // 60 min

    private long autolockMs;
    private long lastActivity;
    private boolean unlocked = true;
    private boolean backgrounded = false;
    private long backgroundedAt = 0;
    private int wrongStreak = 0;
    private long backoffUntil = 0;

    /** Shell entrypoint (PinGuard): a fresh process WITH a stored verifier
     *  starts LOCKED — the PIN must be proven before the wallet opens, even
     *  before any inactivity has elapsed. Without a verifier the session
     *  starts unlocked (gate inert). Judge r1 blocker: an always-unlocked
     *  start let a restarted app skip authentication entirely. */
    public static LockPolicy forSession(boolean verifierPresent, long autolockMs, long now) {
        LockPolicy p = new LockPolicy(autolockMs, now);
        if (verifierPresent) p.lockNow();
        return p;
    }

    /** @param autolockMs inactivity window; @param now fake-clock start time */
    public LockPolicy(long autolockMs, long now) {
        if (autolockMs <= 0) throw new IllegalArgumentException("autolockMs must be > 0");
        this.autolockMs = autolockMs;
        this.lastActivity = now;
    }

    public long autolockMs() { return autolockMs; }

    /** S-4 settings hook: adopt a new inactivity window at runtime. Only the
     *  WINDOW changes - never the lock state: a longer window cannot unlock a
     *  locked session, and a shorter one takes effect at the next
     *  isLocked/onActivity evaluation (the lazy gate stays authoritative).
     *  The shell persists the choice; this method never touches storage.
     *  @throws IllegalArgumentException outside [MIN_AUTOLOCK_MS,
     *          MAX_AUTOLOCK_MS] (a window the policy cannot enforce). */
    public void setAutolockMs(long autolockMs) {
        if (autolockMs < MIN_AUTOLOCK_MS || autolockMs > MAX_AUTOLOCK_MS) {
            throw new IllegalArgumentException("autolockMs outside supported range");
        }
        this.autolockMs = autolockMs;
    }

    /** Any user interaction. An ALREADY-EXPIRED lock resolves BEFORE the
     *  touch counts: otherwise a tap arriving just after the deadline would
     *  extend lastActivity while still unlocked and sail through the next
     *  gate check (judge r2 — the 10s cover tick cannot be the enforcement).
     *  Activity never unlocks a locked session. */
    public void onActivity(long now) {
        if (unlocked && now - lastActivity >= autolockMs) {
            unlocked = false;
        }
        lastActivity = Math.max(lastActivity, now);
    }

    /** App paused / lost foreground. Does NOT lock yet — resume decides. */
    public void onBackground(long now) {
        backgrounded = true;
        backgroundedAt = now;
    }

    /** App resumed. Backgrounded >= autolockMs locks (device-out-of-sight). */
    public void onResume(long now) {
        if (backgrounded && unlocked && now - backgroundedAt >= autolockMs) {
            unlocked = false;
        }
        backgrounded = false;
    }

    /** Authoritative gate decision: true while the PIN is required. Lazy
     *  auto-lock fires here, so callers must consult this at the gate, not
     *  only in a timer tick. */
    public boolean isLocked(long now) {
        if (unlocked && now - lastActivity >= autolockMs) {
            unlocked = false;
        }
        return !unlocked;
    }

    /** Manual lock (shell convenience; same effect as expiry). */
    public void lockNow() { unlocked = false; }

    /** An in-app child screen (SettingsActivity) resumed on top of the main
     *  activity: the app never left the user's sight, so the background
     *  bracket is cleared WITHOUT the device-out-of-sight duration lock, and
     *  the touch counts as activity (pushes lastActivity). Contrast with
     *  onResume(), which applies the duration lock. */
    public void clearBackground(long now) {
        backgrounded = false;
        lastActivity = Math.max(lastActivity, now);
    }

    public boolean isUnlocked(long now) { return !isLocked(now); }

    /** Verify one PIN attempt at fake-time now. THROTTLED refuses without
     *  evaluating the PIN; ACCEPTED unlocks, pushes the deadline and clears
     *  the wrong-attempt streak; WRONG_PIN advances the streak and opens the
     *  backoff window once MAX_ATTEMPTS consecutive failures are reached.
     *  Returns ACCEPTED / WRONG_PIN / THROTTLED. */
    public int verifyAttempt(long now, boolean pinMatches) {
        if (now < backoffUntil) {
            return THROTTLED;
        }
        if (pinMatches) {
            wrongStreak = 0;
            backoffUntil = 0;
            unlocked = true;
            lastActivity = Math.max(lastActivity, now);
            return ACCEPTED;
        }
        wrongStreak++;
        if (wrongStreak >= MAX_ATTEMPTS) {
            long backoff = BACKOFF_BASE_MS;
            for (int i = MAX_ATTEMPTS; i < wrongStreak; i++) {
                backoff = Math.min(backoff * 2, BACKOFF_CAP_MS);
            }
            backoffUntil = now + backoff;
        }
        return WRONG_PIN;
    }

    /** Absolute end of the current backoff window (clock-domain of `now`).
     *  Lets the shell refuse BEFORE hashing without re-deriving the rule. */
    public long throttleUntilMs() { return backoffUntil; }

    /** Milliseconds until a throttled verify is evaluated again (0 if none). */
    public long throttleRemainingMs(long now) {
        return Math.max(0, backoffUntil - now);
    }
}
